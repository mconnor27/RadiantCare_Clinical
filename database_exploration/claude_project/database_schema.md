# Database Schema Documentation
## Varian Data Warehouse Schema


## Schema: DWH
Tables: 288

### DWH.AppendDoseHelper
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `CountOfRows` VDT_INT NOT NULL 

---

### DWH.AttributeCustomGrouping
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `AttributeCustomGroupingID` VDT_SERIALNUMBER NOT NULL [PK]
- `CustomGroupID` VDT_SERIALNUMBER NOT NULL 
- `DimTablePrimaryID` VDT_SERIALNUMBER NOT NULL 
- `DimTableName` VDT_STRING512 NOT NULL 
- `ColumnName` VDT_STRING512 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.AttributeMetaData
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `AttributeMetaDataID` VDT_SERIALNUMBER NOT NULL [PK]
- `DatasetName` VDT_STRING64 NOT NULL 
- `DatasetAttributeName` VDT_STRING64 NOT NULL 
- `TableAttributeName` VDT_STRING512 NOT NULL 
- `TableName` VDT_STRING64 NOT NULL 
- `IsRealTime` bit NOT NULL 

---

### DWH.AuraConfiguration
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_INT NOT NULL [PK]
- `Key` VDT_STRING32 NOT NULL 
- `KeyValue` VDT_STRING1024 NOT NULL 

---

### DWH.AuraDBHistory
**Columns:** 8 | **Foreign Keys:** 0

**Columns:**
- `AuraDBHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `EventType` VDT_STRING64 NOT NULL 
- `StartingRelease` VDT_STRING64 NOT NULL 
- `EndingRelease` VDT_STRING64 NOT NULL 
- `Description` VDT_STRING254 NOT NULL 
- `UpgrVersion` VDT_STRING32 NOT NULL 
- `InstalledDateTime` VDT_DATETIME NOT NULL 
- `UnInstalledDateTime` VDT_DATETIME NOT NULL 

---

### DWH.AuraReleaseVersion
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `AuraReleaseVersionID` int NOT NULL [PK]
- `VersionNumber` varchar NOT NULL 
- `ReleaseDescription` varchar NOT NULL 
- `IsSFA` bit NOT NULL 
- `VersionSequenceNumber` int NOT NULL 

---

### DWH.AuraUpgradeRuleSet
**Columns:** 17 | **Foreign Keys:** 0

**Columns:**
- `UpgradeRuleID` int NOT NULL [PK]
- `PackageName` varchar NOT NULL 
- `RuleName` varchar NOT NULL 
- `RuleDescription` varchar NOT NULL 
- `RuleType` varchar NOT NULL 
- `SourceRelease` varchar NOT NULL 
- `IsActive` int NOT NULL 
- `ExecStartTime` datetime NOT NULL 
- `ExecEndTime` datetime NOT NULL 
- `CompletedStatus` int NOT NULL 
- `InProgressStatus` int NOT NULL 
- `IsRuleConditionSatisfied` tinyint NOT NULL 
- `IsDRFix` int NOT NULL 
- `DRDetail` nchar NOT NULL 
- `RuleSQL` nvarchar NOT NULL 
- `RuleConditionExecDatabase` varchar NOT NULL 
- `RuleExecSequence` int NOT NULL 

---

### DWH.AuraUpgradeRuleSetExecHistory
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `UpgradeRuleID` int NOT NULL 
- `LogId` bigint NOT NULL 
- `PackageName` varchar NOT NULL 
- `RuleName` varchar NOT NULL 
- `ExecStartTime` datetime NOT NULL 
- `ExecEndTime` datetime NOT NULL 
- `CompletedStatus` int NOT NULL 
- `InProgressStatus` int NOT NULL 
- `IsRuleConditionSatisfied` tinyint NOT NULL 
- `CompletedWithError` int NOT NULL 
- `UpgradeCompleteDateTime` datetime NOT NULL 

---

### DWH.BrachyTreatmentModel
**Columns:** 73 | **Foreign Keys:** 0

**Columns:**
- `RadiationHstryType` VDT_TYPE NOT NULL 
- `TreatmentDeliveryType` VDT_STRING16 NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `RadiationName` VDT_STRING64 NOT NULL 
- `RadiationNumber` VDT_INT NOT NULL 
- `TechniqueLabel` VDT_STRING64 NOT NULL 
- `RadiationType` VDT_ENERGYMODE NOT NULL 
- `TreatmentStartTime` VDT_DATETIME NOT NULL 
- `TreatmentEndTime` VDT_DATETIME NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanMachineID` VDT_SERIALNUMBER NOT NULL 
- `DimActualMachineID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentStartDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentEndDate` VDT_SERIALNUMBER NOT NULL 
- `TreatmentTime` VDT_TIME NOT NULL 
- `TreatmentTimeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TerminationStatus` VDT_STATUS16 NOT NULL 
- `FractionNumber` VDT_INT NOT NULL 
- `ApprovalDate` VDT_DATETIME NOT NULL 
- `DimDateID_CourseStartDateTime` VDT_SERIALNUMBER NOT NULL 
- `UserName1` VDT_NAME NOT NULL 
- `UserName2` VDT_STRING32 NOT NULL 
- `UserName3` VDT_STRING32 NOT NULL 
- `OverrideFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `HistoryNote` VDT_STRING NOT NULL 
- `MachineNote` VDT_STRING NOT NULL 
- `FieldSetupNote` VDT_STRING NOT NULL 
- `PlanTreatmentType` VDT_TREATMENTTYPE NOT NULL 
- `PrescribedPercentage` VDT_FLOAT NOT NULL 
- `PrescribedDose` VDT_DOSE NOT NULL 
- `CourseCompletedDateTime` VDT_DATETIME NOT NULL 
- `CourseStartDateTime` VDT_DATETIME NOT NULL 
- `DimDateID_CourseCompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_RadiationHstryApprovalDate` VDT_SERIALNUMBER NOT NULL 
- `CourseClinicalStatus` VDT_CLINICALSTATUS NOT NULL 
- `ActualDose` VDT_DOSE NOT NULL 
- `BrachyTreatmentType` VDT_STRING16 NOT NULL 
- `ChannelNumber` VDT_INT NOT NULL 
- `ChannelLength` VDT_FLOAT NOT NULL 
- `SpecifiedChannelTotalTime` VDT_FLOAT NOT NULL 
- `ChannelReferenceAirKerma` VDT_FLOAT NOT NULL 
- `DeliveredChannelTotalTime` VDT_FLOAT NOT NULL 
- `SpecifiedNumberOfPulses` VDT_INT NOT NULL 
- `DeliveredNumberOfPulses` VDT_INT NOT NULL 
- `SpecifiedPulseRepetitionInterval` VDT_FLOAT NOT NULL 
- `DeliveredPulseRepetitionInterval` VDT_FLOAT NOT NULL 
- `SourceSerialNumber` VDT_MANUFACTSERIALNO NOT NULL 
- `SourceIsotopeName` VDT_NAME NOT NULL 
- `ReferenceAirKermaRate` VDT_FLOAT NOT NULL 
- `SourceStrengthReferenceDateTime` VDT_DATETIME NOT NULL 
- `NumberOfSourcePositions` VDT_INT NOT NULL 
- `TreatmentRecordActualMachineAuthorization` VDT_NAME NOT NULL 
- `TreatmentRecordMachOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TreatmentRecordHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `TreatmentRecordHstryTaskName` VDT_TASKNAME NOT NULL 
- `TreatmentRecordTreatmentRecordDateTime` VDT_DATETIMESTAMP NOT NULL 
- `TreatmentRecordNoOfFractions` VDT_COUNT NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCourseSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointHstrySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActualMachineSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlannedMachineSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTreatmentRecordSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRadiationSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRadiationHstrySer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.ChartQATreatment
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `LastChartQADate` VDT_DATETIMESTAMP NOT NULL 
- `ctrChartQATreatmentSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `ctrChartQASer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.CourseModel
**Columns:** 19 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_STRING16 NOT NULL 
- `CourseStartDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ClinicalStatus` VDT_CLINICALSTATUS NOT NULL 
- `FirstTreatmentDate` VDT_DATETIMESTAMP NOT NULL 
- `LastTreatmentDate` VDT_DATETIMESTAMP NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDuration` VDT_INT NOT NULL 
- `Comment` VDT_STRING254 NOT NULL 
- `CompletedDateTime` VDT_DATETIME NOT NULL 
- `TreatmentIntentType` VDT_STRING64 NOT NULL 
- `PhysicianIntentSer` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.CustomGroup
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `CustomGroupID` VDT_SERIALNUMBER NOT NULL [PK]
- `CustomGroupName` VDT_STRING512 NOT NULL 
- `HierarchyLevel` VDT_INT NOT NULL 
- `ParentID` VDT_INT NOT NULL 
- `TableName` VDT_STRING512 NOT NULL 
- `ColumnName` VDT_STRING512 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.CustomGrouping
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `CustomGroupingID` VDT_SERIALNUMBER NOT NULL [PK]
- `ColumnToMap` VDT_STRING512 NOT NULL 
- `GroupLevel1` VDT_STRING512 NOT NULL 
- `GroupLevel2` VDT_STRING512 NOT NULL 
- `GroupLevel3` VDT_STRING512 NOT NULL 
- `GroupLevel4` VDT_STRING512 NOT NULL 
- `GroupLevel5` VDT_STRING512 NOT NULL 

---

### DWH.CustomGroupingRequiredList
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `TableName` VDT_STRING512 NOT NULL 
- `ColumnName` VDT_STRING512 NOT NULL 
- `Description1` VDT_STRING512 NOT NULL 
- `Description2` VDT_STRING512 NOT NULL 
- `Description3` VDT_STRING512 NOT NULL 

---

### DWH.DVHInputParameters
**Columns:** 12 | **Foreign Keys:** 0

**Columns:**
- `DVHInputParameterID` VDT_SERIALNUMBER NOT NULL [PK]
- `PatientDbKey` VDT_SERIALNUMBER NOT NULL 
- `CourseDbKey` VDT_SERIALNUMBER NOT NULL 
- `PlanDbKey` VDT_SERIALNUMBER NOT NULL 
- `StructureSetDbKey` VDT_SERIALNUMBER NOT NULL 
- `StructureDbKey` VDT_SERIALNUMBER NOT NULL 
- `PlanSetUpHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `StructureHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `LoadStatus` varchar NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `Comments` VDT_COMMENT NOT NULL 
- `LastModifyDateTime` VDT_DATETIME NOT NULL 

---

### DWH.DVHInputParametersTempForETL
**Columns:** 12 | **Foreign Keys:** 0

**Columns:**
- `DVHInputParameterID` VDT_SERIALNUMBER NOT NULL 
- `PatientDbKey` VDT_SERIALNUMBER NOT NULL 
- `CourseDbKey` VDT_SERIALNUMBER NOT NULL 
- `PlanDbKey` VDT_SERIALNUMBER NOT NULL 
- `StructureSetDbKey` VDT_SERIALNUMBER NOT NULL 
- `StructureDbKey` VDT_SERIALNUMBER NOT NULL 
- `PlanSetUpHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `StructureHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `LoadStatus` varchar NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `Comments` VDT_COMMENT NOT NULL 
- `LastModifyDateTime` VDT_DATETIME NOT NULL 

---

### DWH.DVHPatientPoints
**Columns:** 8 | **Foreign Keys:** 0

**Columns:**
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimStructureID` VDT_SERIALNUMBER NOT NULL 
- `RelativeVolume` float NOT NULL 
- `PatientId` nvarchar NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `StructureId` VDT_ID NOT NULL 
- `PlanSetupName` VDT_NAME NOT NULL 

---

### DWH.DataModelList
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `DataModelListID` VDT_SERIALNUMBER NOT NULL [PK]
- `ModelName` varchar NOT NULL 
- `LastVersion` bigint NOT NULL 
- `PreviousVersion` bigint NOT NULL 
- `SourceVersion_System` bigint NOT NULL 
- `SourceVersion_Enm` bigint NOT NULL 

---

### DWH.DataReconciliationResult
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `ParentLogID` bigint NOT NULL 
- `SourceTableName` sysname NOT NULL 
- `SourceCount` int NOT NULL 
- `DWTableName` sysname NOT NULL 
- `DWCount` int NOT NULL 
- `IsMatch` int NOT NULL 

---

### DWH.DeleteMetadata
**Columns:** 14 | **Foreign Keys:** 0

**Columns:**
- `DeleteMetadataID` VDT_INT NOT NULL 
- `DeleteOperationStep` VDT_STRING128 NOT NULL 
- `TableName` VDT_STRING128 NOT NULL 
- `TableAlias` VDT_STRING128 NOT NULL 
- `Jointype` VDT_STRING25 NOT NULL 
- `TableSequence` VDT_INT NOT NULL 
- `JoinCondition` VDT_STRING512 NOT NULL 
- `WhereCondition` VDT_STRING128 NOT NULL 
- `IsIncremental` VDT_TINYINT NOT NULL 
- `IsUpgrade` VDT_TINYINT NOT NULL 
- `IsFlatDelete` VDT_TINYINT NOT NULL 
- `FlatDeleteQuery` VDT_STRING1024 NOT NULL 
- `IsActive` VDT_TINYINT NOT NULL 
- `InsUpdtDate` VDT_DATETIME NOT NULL 

---

### DWH.DimActInstTemplateLink
**Columns:** 12 | **Foreign Keys:** 1

**Columns:**
- `DimActInstTemplateLinkID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimTemplateCycleID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityID` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPredecessorSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTemplateCycleSer` VDT_SERIALNUMBER NOT NULL 
- `TemplateCycleRevCount` VDT_INT NOT NULL 
- `ctrActivityInstanceLinkSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityInstanceLinkRevCount` VDT_INT NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `ActivityInstanceStatus` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimTemplateCycleID` → `DWH.DimTemplateCycle.DimTemplateCycleID`

---

### DWH.DimActivity
**Columns:** 31 | **Foreign Keys:** 0

**Columns:**
- `DimActivityID` VDT_SERIALNUMBER NOT NULL [PK]
- `ActivityCategoryCode` VDT_STRING64 NOT NULL 
- `ActivityCategoryENU` VDT_STRING256 NOT NULL 
- `ActivityCategoryFRA` VDT_STRING256 NOT NULL 
- `ActivityCategoryESN` VDT_STRING256 NOT NULL 
- `ActivityCategoryCHS` VDT_STRING256 NOT NULL 
- `ActivityCategoryDEU` VDT_STRING256 NOT NULL 
- `ActivityCategoryITA` VDT_STRING256 NOT NULL 
- `ActivityCategoryJPN` VDT_STRING256 NOT NULL 
- `ActivityCategoryPTB` VDT_STRING256 NOT NULL 
- `ActivityCategorySVE` VDT_STRING256 NOT NULL 
- `ActivityCode` VDT_STRING64 NOT NULL 
- `ActivityNameENU` VDT_STRING256 NOT NULL 
- `ActivityNameFRA` VDT_STRING256 NOT NULL 
- `ActivityNameESN` VDT_STRING256 NOT NULL 
- `ActivityNameCHS` VDT_STRING256 NOT NULL 
- `ActivityNameDEU` VDT_STRING256 NOT NULL 
- `ActivityNameITA` VDT_STRING256 NOT NULL 
- `ActivityNameJPN` VDT_STRING256 NOT NULL 
- `ActivityNamePTB` VDT_STRING256 NOT NULL 
- `ActivityNameSVE` VDT_STRING256 NOT NULL 
- `ActivityType` nvarchar NOT NULL 
- `LastModifiedOn` VDT_DATETIMESTAMP NOT NULL 
- `ActivityRevCount` VDT_REVISIONCOUNT NOT NULL 
- `DefaultDuration` VDT_TIMESLOT NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimLookupID_ActivityObjectStatus` VDT_SERIALNUMBER NOT NULL 
- `EffectiveStartDate` VDT_DATETIME NOT NULL 
- `EffectiveEndDate` VDT_DATETIME NOT NULL 

---

### DWH.DimActivityAttribute
**Columns:** 10 | **Foreign Keys:** 1

**Columns:**
- `DimActivityAttributeID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityID` VDT_SERIALNUMBER NOT NULL 
- `UserDefActAttrId` VDT_ID NOT NULL 
- `Description` VDT_STRING254 NOT NULL 
- `UserDefActAttrRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ctrUserDefActAttrSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityAttributeSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityAttributeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActivityAttributeObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimActivityID` → `DWH.DimActivity.DimActivityID`

---

### DWH.DimActivityTransaction
**Columns:** 58 | **Foreign Keys:** 17

**Columns:**
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceGroupID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AppointmentStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ActualResourceType` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ActivityCreatedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ActivityCompletedBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ScheduledEndTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AppointmentDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ActivityStartDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ActivityEndDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PatientArrivalDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID_VisitUser` VDT_SERIALNUMBER NOT NULL 
- `ScheduledEndTime` VDT_DATETIME NOT NULL 
- `AppointmentDateTime` VDT_DATETIME NOT NULL 
- `IsScheduled` VDT_STRING1 NOT NULL 
- `ActivityStartDateTime` VDT_DATETIME NOT NULL 
- `ActivityEndDateTime` VDT_DATETIME NOT NULL 
- `ActivityPriority` VDT_STRING64 NOT NULL 
- `ActivityNote` nvarchar NOT NULL 
- `CheckedIn` VDT_STRING1 NOT NULL 
- `PatientArrivalDateTime` VDT_DATETIME NOT NULL 
- `PatientLocation` VDT_STRING256 NOT NULL 
- `WaitListedFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceGroupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCreatedByResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityInstanceRevCount` VDT_REVISIONCOUNT NOT NULL 
- `AppointmentStatus` VDT_STRING64 NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimDateID_CreationDate` VDT_SERIALNUMBER NOT NULL 
- `AppointmentInstanceFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `MOROIndicator` VDT_STRING10 NOT NULL 
- `DimMOTreatmentPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimClinicID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_CancelReasonType` VDT_SERIALNUMBER NOT NULL 
- `VisitCycleNumber` VDT_INT NOT NULL 
- `VisitCycleDay` VDT_INT NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `DimMedoncPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimMedoncPlanPhaseID` VDT_SERIALNUMBER NOT NULL 
- `DerivedAppointmentTaskDate` VDT_DATETIME NOT NULL 
- `DimLookupID_AppointmentResourceStatus` VDT_SERIALNUMBER NOT NULL 
- `AppointmentResourceStatus` VDT_STRING64 NOT NULL 
- `DxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 
- `ActivityOwnerFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `IsVisitTypeOpenChart` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `AppointmentDateTimeFloatValue` float NOT NULL 
- `WorkFlowActiveFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 

**Foreign Keys:**
- `DimActivityID` → `DWH.DimActivity.DimActivityID`
- `DimResourceID` → `DWH.DimResource.DimResourceID`
- `DimResourceGroupID` → `DWH.DimResourceGroup.DimResourceGroupID`
- `DimLookupID_AppointmentStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ActualResourceType` → `DWH.DimLookup.DimLookupID`
- `DimUserID_ActivityCreatedBy` → `DWH.DimUser.DimUserID`
- `DimDateID_ScheduledEndTime` → `DWH.DimDate.DimDateID`
- `DimDateID_AppointmentDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ActivityStartDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ActivityEndDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_PatientArrivalDateTime` → `DWH.DimDate.DimDateID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimHospitalDepartmentID_VisitUser` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimDateID_CreationDate` → `DWH.DimDate.DimDateID`
- `DimMedoncPlanID` → `DWH.DimMedoncPlan.DimMedoncPlanID`
- `DimMedoncPlanPhaseID` → `DWH.DimMedoncPlanPhase.DimMedoncPlanPhaseID`

---

### DWH.DimActivityTransactionHistory
**Columns:** 69 | **Foreign Keys:** 16

**Columns:**
- `DimActivityTransactionHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceGroupID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AppointmentStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ActualResourceType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AppointmentResourceStatus` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ActivityCreatedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ActivityCompletedBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ScheduledEndTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AppointmentDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ActivityStartDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ActivityEndDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PatientArrivalDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreationDate` VDT_SERIALNUMBER NOT NULL 
- `IsScheduled` VDT_STRING1 NOT NULL 
- `CheckedIn` VDT_STRING1 NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ScheduledActivityRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCreatedByResourceSer` VDT_SERIALNUMBER NOT NULL 
- `CreationDate` VDT_DATETIME NOT NULL 
- `WaitListedFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ScheduledStartTime` VDT_DATETIME NOT NULL 
- `Priority` VDT_STRING64 NOT NULL 
- `ActualStartDate` VDT_DATETIME NOT NULL 
- `ActualEndDate` VDT_DATETIME NOT NULL 
- `ScheduledActivityCode` VDT_STRING64 NOT NULL 
- `ActivityNote` VDT_STRING254 NOT NULL 
- `ScheduledActivityHstryDateTime` VDT_DATETIME NOT NULL 
- `ScheduledActivityObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityInstanceRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ctrTemplateCycleSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 
- `ctrDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPredecessorSer` VDT_SERIALNUMBER NOT NULL 
- `AppointmentInstanceFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `Duration` VDT_INT NOT NULL 
- `PriorPostDueDurUnits` VDT_TIMESLOT NOT NULL 
- `ExclusiveFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ActivityInstanceHstryDateTime` VDT_DATETIME NOT NULL 
- `ActivityInstanceObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 
- `AttendeeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceGroupSer` VDT_SERIALNUMBER NOT NULL 
- `AttendeeExclusiveFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `PrimaryFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ActivityOwnerFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ParticipationRole` VDT_STRING32 NOT NULL 
- `AttendeeHstryDateTime` VDT_DATETIME NOT NULL 
- `AttendeeObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ctrPatientLocationSer` VDT_SERIALNUMBER NOT NULL 
- `PatientLocationRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ctrVenueSer` VDT_SERIALNUMBER NOT NULL 
- `ArrivalDateTime` VDT_DATETIME NOT NULL 
- `Comment` VDT_STRING254 NOT NULL 
- `PatientLocationHstryDateTime` VDT_DATETIME NOT NULL 
- `ActivityRevCount` VDT_REVISIONCOUNT NOT NULL 
- `TemplateCycleRevCount` VDT_REVISIONCOUNT NOT NULL 
- `AppointmentDependentFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ActInstReadOnly` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `WorkFlowActiveFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `LogID` VDT_SERIALNUMBER NOT NULL 

**Foreign Keys:**
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimActivityID` → `DWH.DimActivity.DimActivityID`
- `DimResourceID` → `DWH.DimResource.DimResourceID`
- `DimResourceGroupID` → `DWH.DimResourceGroup.DimResourceGroupID`
- `DimLookupID_AppointmentStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ActualResourceType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_AppointmentResourceStatus` → `DWH.DimLookup.DimLookupID`
- `DimUserID_ActivityCreatedBy` → `DWH.DimUser.DimUserID`
- `DimDateID_ScheduledEndTime` → `DWH.DimDate.DimDateID`
- `DimDateID_AppointmentDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ActivityStartDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ActivityEndDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_PatientArrivalDateTime` → `DWH.DimDate.DimDateID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimDateID_CreationDate` → `DWH.DimDate.DimDateID`

---

### DWH.DimActivityTransactionWorkTable
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL [PK]
- `DxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 
- `NewDxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 

---

### DWH.DimAddOn
**Columns:** 8 | **Foreign Keys:** 1

**Columns:**
- `DimAddOnID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `AddOnId` VDT_ID NOT NULL 
- `AddOnName` VDT_NAME NOT NULL 
- `AddOnType` VDT_TABLENAME NOT NULL 
- `AddOnSubType` VDT_TABLENAME NOT NULL 
- `AddOnSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMachineID` → `DWH.DimMachine.DimMachineID`

---

### DWH.DimAgendaTemplate
**Columns:** 10 | **Foreign Keys:** 1

**Columns:**
- `DimAgendaTemplateID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `AgendaTemplateDescription` VDT_STRING50 NOT NULL 
- `ActiveEntryIndicator` VDT_STRING1 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `UseEncounterDateIndicator` VDT_STRING1 NOT NULL 
- `ctrinst_id` VDT_STRING60 NOT NULL 
- `ctragenda_template_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimAgendaTemplateGroupTask
**Columns:** 19 | **Foreign Keys:** 3

**Columns:**
- `DimAgendaTemplateGroupTaskID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimAgendaTemplateID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AgendaTask` VDT_SERIALNUMBER NOT NULL 
- `AgendaTemplateGroupDesc` VDT_STRING50 NOT NULL 
- `AgendaTemplateGroupSeqNumber` VDT_INT NOT NULL 
- `AgendaTempGrpTransLogDateTime` VDT_DATETIME NOT NULL 
- `AgendaTempGrpTransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `AgendaTemplateTaskDesc` VDT_STRING50 NOT NULL 
- `AgendaTemplatTaskSeqNumber` VDT_INT NOT NULL 
- `CustomizationXML` VDT_STRING1024 NOT NULL 
- `RequiredIndicator` VDT_STRING1 NOT NULL 
- `AgendaTempTaskTransLogDateTime` VDT_DATETIME NOT NULL 
- `AgendaTempTaskTransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `ctragenda_template_id` VDT_INT NOT NULL 
- `ctragenda_template_group_id` VDT_INT NOT NULL 
- `ctragenda_template_task_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimAgendaTemplateID` → `DWH.DimAgendaTemplate.DimAgendaTemplateID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimLookupID_AgendaTask` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimAgendaTemplateTaskUser
**Columns:** 12 | **Foreign Keys:** 3

**Columns:**
- `DimAgendaTemplateTaskUserID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimAgendaTemplateGroupTaskID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_TemplateTaskUser` VDT_SERIALNUMBER NOT NULL 
- `SequenceNumber` VDT_INT NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctruser_inst_id` VDT_STRING30 NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `ctragenda_template_id` VDT_INT NOT NULL 
- `ctragenda_template_task_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimAgendaTemplateGroupTaskID` → `DWH.DimAgendaTemplateGroupTask.DimAgendaTemplateGroupTaskID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimUserID_TemplateTaskUser` → `DWH.DimUser.DimUserID`

---

### DWH.DimBrachyApplicator
**Columns:** 23 | **Foreign Keys:** 1

**Columns:**
- `DimBrachyApplicatorID` VDT_SERIALNUMBER NOT NULL [PK]
- `BrachyApplicatorId` VDT_ID NOT NULL 
- `BrachyApplicatorName` VDT_NAME NOT NULL 
- `BrachyApplicatorTypeInfo` VDT_STRING16 NOT NULL 
- `DefaultLength` VDT_FLOAT NOT NULL 
- `ManufacturerName` VDT_STRING254 NOT NULL 
- `NoOfShapePoints` VDT_INT NOT NULL 
- `Shape` VDT_CONTOURPOINTS NOT NULL 
- `NoOfSourceGeom` VDT_INT NOT NULL 
- `SourceGeometry` image NOT NULL 
- `WallMaterialId` VDT_STRING16 NOT NULL 
- `WallNominalTransmission` VDT_FLOAT NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `StepSize` VDT_FLOAT NOT NULL 
- `FirstSourcePosition` VDT_FLOAT NOT NULL 
- `LastSourcePosition` VDT_FLOAT NOT NULL 
- `SeparateSources` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `DefaultChannelNumber` VDT_INT NOT NULL 
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `DeadSpace` VDT_FLOAT NOT NULL 
- `ctrBrachyApplicatorSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimUserID` → `DWH.DimUser.DimUserID`

---

### DWH.DimBrachyField
**Columns:** 24 | **Foreign Keys:** 4

**Columns:**
- `DimBrachyFieldID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimChannnelID` VDT_SERIALNUMBER NOT NULL 
- `DimBrachyApplicatorID` VDT_SERIALNUMBER NOT NULL 
- `BrachyFieldTypeInfo` VDT_STRING32 NOT NULL 
- `ApplicatorLength` VDT_FLOAT NOT NULL 
- `PlannedTreatmDateTime` VDT_DATETIME NOT NULL 
- `StepSize` VDT_FLOAT NOT NULL 
- `FirstSourcePosition` VDT_FLOAT NOT NULL 
- `LastSourcePosition` VDT_FLOAT NOT NULL 
- `AutomaticPosFlag` VDT_FLAG NOT NULL 
- `ApplicatorPartChannelUID` VDT_INT NOT NULL 
- `DimPlanID_BrachySolidApplicator` VDT_SERIALNUMBER NOT NULL 
- `DeadSpace` VDT_FLOAT NOT NULL 
- `BrachySolidApplicatorId` VDT_ID NOT NULL 
- `BrachySolidApplicatorName` VDT_NAME NOT NULL 
- `BrachySolidApplicatorApplicatorPartUID` VDT_STRING64 NOT NULL 
- `BrachySolidApplicatorPartFileName` VDT_FILENAME NOT NULL 
- `BrachySolidApplicatorComment` VDT_COMMENT NOT NULL 
- `BrachySolidApplicatorDimUserID` VDT_SERIALNUMBER NOT NULL 
- `BrachySolidApplicatorHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ctrBrachySolidApplicatorSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRadiationSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimFieldID` → `DWH.DimField.DimFieldID`
- `DimChannnelID` → `DWH.DimChannel.DimChannelID`
- `DimBrachyApplicatorID` → `DWH.DimBrachyApplicator.DimBrachyApplicatorID`
- `BrachySolidApplicatorDimUserID` → `DWH.DimUser.DimUserID`

---

### DWH.DimCellType
**Columns:** 16 | **Foreign Keys:** 0

**Columns:**
- `DimCellTypeID` VDT_SERIALNUMBER NOT NULL [PK]
- `CellTypeBehaviorCode` VDT_STRING2 NOT NULL 
- `ClsSchemeId` VDT_INT NOT NULL 
- `MorphCode` VDT_STRING10 NOT NULL 
- `MorphCodeSequence` VDT_INT NOT NULL 
- `VarisHistologyCode` VDT_STRING32 NOT NULL 
- `CellTypeENU` VDT_STRING254 NOT NULL 
- `CellTypeFRA` VDT_STRING254 NOT NULL 
- `CellTypeESN` VDT_STRING254 NOT NULL 
- `CellTypeCHS` VDT_STRING254 NOT NULL 
- `CellTypeDEU` VDT_STRING254 NOT NULL 
- `CellTypeITA` VDT_STRING254 NOT NULL 
- `CellTypeJPN` VDT_STRING254 NOT NULL 
- `CellTypePTB` VDT_STRING254 NOT NULL 
- `CellTypeSVE` VDT_STRING254 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimChannel
**Columns:** 12 | **Foreign Keys:** 2

**Columns:**
- `DimChannelID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `ChannelId` VDT_ID NOT NULL 
- `ChannelName` VDT_NAME NOT NULL 
- `ChannelNumber` VDT_NUMBER NOT NULL 
- `MinLength` VDT_FLOAT NOT NULL 
- `MaxLength` VDT_FLOAT NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ctrChannelSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMachineID` → `DWH.DimMachine.DimMachineID`
- `DimUserID` → `DWH.DimUser.DimUserID`

---

### DWH.DimChartQA
**Columns:** 7 | **Foreign Keys:** 1

**Columns:**
- `DimChartQAID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `ChartQADateTime` VDT_DATETIME NOT NULL 
- `ChartQAComment` VDT_STRING1024 NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ctrChartQASer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.DimClinic
**Columns:** 6 | **Foreign Keys:** 1

**Columns:**
- `DimClinicID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `ClinicName` VDT_STRING100 NOT NULL 
- `ActiveEntryInd` VDT_STRING2 NOT NULL 
- `ctrclinic_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimConstantResource
**Columns:** 21 | **Foreign Keys:** 1

**Columns:**
- `DimConstantResourceID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimLookupID_ResourceType` VDT_SERIALNUMBER NOT NULL 
- `ResourceId` VDT_ID NOT NULL 
- `ResourceFullName` VDT_STRING128 NOT NULL 
- `ResourceAliasName` VDT_NAME NOT NULL 
- `ResourceTypeNum` VDT_NUMBER NOT NULL 
- `ResourceObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `Schedulable` varchar NOT NULL 
- `ResourceCompleteAddress` VDT_STRING512 NOT NULL 
- `IsPrimaryResourceAddress` VDT_INT NOT NULL 
- `ResourceAddressType` VDT_STRING64 NOT NULL 
- `ResourceAddressComment` VDT_COMMENT NOT NULL 
- `ResourcePrimaryPhoneNumber` VDT_PHONENUMBER NOT NULL 
- `ResourceSecondaryPhoneNumber` VDT_PHONENUMBER NOT NULL 
- `ResourcePagerNumber` VDT_PHONENUMBER NOT NULL 
- `ResourceFaxNumber` VDT_PHONENUMBER NOT NULL 
- `ResourceEMailAddress` VDT_STRING64 NOT NULL 
- `ResourceOriginationDate` VDT_DATETIME NOT NULL 
- `ResourceTerminationDate` VDT_DATETIME NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimLookupID_ResourceType` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimCourse
**Columns:** 15 | **Foreign Keys:** 2

**Columns:**
- `DimCourseID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_STRING16 NOT NULL 
- `CourseStartDateTime` VDT_DATETIMESTAMP NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDuration` VDT_INT NOT NULL 
- `Comment` VDT_STRING254 NOT NULL 
- `ctrCourseSer` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ClinicalStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TreatmentIntentType` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimDxSiteID` → `DWH.DimDxSite.DimDxSiteID`

---

### DWH.DimDate
**Columns:** 40 | **Foreign Keys:** 0

**Columns:**
- `DimDateID` VDT_SERIALNUMBER NOT NULL [PK]
- `Date` VDT_DATETIME NOT NULL 
- `DateValueInt` VDT_INT NOT NULL 
- `FullDateDesc` VDT_STRING50 NOT NULL 
- `CalMonthNo` VDT_INT NOT NULL 
- `CalQuarterNo` VDT_INT NOT NULL 
- `CalHalfYearNo` VDT_INT NOT NULL 
- `CalYearNo` VDT_INT NOT NULL 
- `CalMonthName` VDT_STRING50 NOT NULL 
- `CalMonthFirstDate` VDT_DATETIME NOT NULL 
- `CalMonthLastDate` VDT_DATETIME NOT NULL 
- `DaysInCalMonth` VDT_INT NOT NULL 
- `CalQuarterName` VDT_STRING50 NOT NULL 
- `CalQuarterFirstDate` VDT_DATETIME NOT NULL 
- `CalQuarterLastDate` VDT_DATETIME NOT NULL 
- `DaysInCalQuarter` VDT_INT NOT NULL 
- `CalHalfYearName` VDT_STRING50 NOT NULL 
- `CalHalfYearFirstDate` VDT_DATETIME NOT NULL 
- `CalHalfYearLastDate` VDT_DATETIME NOT NULL 
- `DaysInCalHalfYear` VDT_INT NOT NULL 
- `CalYearFirstDate` VDT_DATETIME NOT NULL 
- `CalYearLastDate` VDT_DATETIME NOT NULL 
- `DaysInCalYear` VDT_INT NOT NULL 
- `CalYYYYMM` VDT_STRING50 NOT NULL 
- `CalYYYYQuarter` VDT_STRING50 NOT NULL 
- `CalYYYYHalfYear` VDT_STRING50 NOT NULL 
- `CalYYYY` VDT_STRING50 NOT NULL 
- `LastDayInWeekIndicator` VDT_INT NOT NULL 
- `LastDayInMonthIndicator` VDT_INT NOT NULL 
- `LastDayInQuarterIndicator` VDT_INT NOT NULL 
- `LastDayInHalfYearIndicator` VDT_INT NOT NULL 
- `LastDayInYearIndicator` VDT_INT NOT NULL 
- `HoliDayIndicator` VDT_INT NOT NULL 
- `CalMonthYear` VDT_STRING50 NOT NULL 
- `MonthName` VDT_STRING50 NOT NULL 
- `MonthNum` VDT_INT NOT NULL 
- `MonthWeekNo` VDT_INT NOT NULL 
- `YearWeekName` VDT_STRING50 NOT NULL 
- `MonthWeekName` VDT_STRING50 NOT NULL 
- `YearWeekNo` VDT_INT NOT NULL 

---

### DWH.DimDateRangeController
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `DimDateRangeControllerID` VDT_SERIALNUMBER NOT NULL [PK]
- `ActivityCategory` VDT_STRING64 NOT NULL 
- `AppointmentDateTime` VDT_DATETIME NOT NULL 
- `WaitListedFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimDiagnosisCode
**Columns:** 31 | **Foreign Keys:** 0

**Columns:**
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL [PK]
- `DiagnosisCode` VDT_STRING16 NOT NULL 
- `DiagnosisCodeClsSchemeId` VDT_INT NOT NULL 
- `DiagnosisClinicalDescriptionENU` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionFRA` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionESN` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionCHS` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionDEU` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionITA` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionJPN` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionPTB` VDT_STRING512 NOT NULL 
- `DiagnosisClinicalDescriptionSVE` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleENU` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleFRA` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleESN` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleCHS` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleDEU` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleITA` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleJPN` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitlePTB` VDT_STRING512 NOT NULL 
- `DiagnosisFullTitleSVE` VDT_STRING512 NOT NULL 
- `DiagnosisTableENU` VDT_STRING256 NOT NULL 
- `DiagnosisTableFRA` VDT_STRING256 NOT NULL 
- `DiagnosisTableESN` VDT_STRING256 NOT NULL 
- `DiagnosisTableCHS` VDT_STRING256 NOT NULL 
- `DiagnosisTableDEU` VDT_STRING256 NOT NULL 
- `DiagnosisTableITA` VDT_STRING256 NOT NULL 
- `DiagnosisTableJPN` VDT_STRING256 NOT NULL 
- `DiagnosisTablePTB` VDT_STRING256 NOT NULL 
- `DiagnosisTableSVE` VDT_STRING256 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimDoctor
**Columns:** 30 | **Foreign Keys:** 2

**Columns:**
- `DimDoctorID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimLocationID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ResourceType` VDT_SERIALNUMBER NOT NULL 
- `DoctorFirstName` VDT_NAME NOT NULL 
- `DoctorLastName` VDT_NAME NOT NULL 
- `DoctorFullName` VDT_STRING256 NOT NULL 
- `DoctorAliasName` VDT_NAME NOT NULL 
- `DoctorHonorific` VDT_STRING16 NOT NULL 
- `DoctorNameSuffix` VDT_NAMESUFFIX NOT NULL 
- `DoctorSpecialty` VDT_NAME NOT NULL 
- `DoctorId` VDT_STRING256 NOT NULL 
- `ResourceTypeNum` VDT_NUMBER NOT NULL 
- `ResourceObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `Schedulable` varchar NOT NULL 
- `DoctorCompleteAddress` VDT_STRING512 NOT NULL 
- `IsPrimaryDoctorAddress` VDT_INT NOT NULL 
- `DoctorAddressType` VDT_STRING64 NOT NULL 
- `DoctorAddressComment` VDT_COMMENT NOT NULL 
- `DoctorPrimaryPhoneNumber` VDT_PHONENUMBER NOT NULL 
- `DoctorSecondaryPhoneNumber` VDT_PHONENUMBER NOT NULL 
- `DoctorPagerNumber` VDT_PHONENUMBER NOT NULL 
- `DoctorFaxNumber` VDT_PHONENUMBER NOT NULL 
- `DoctorEMailAddress` VDT_STRING64 NOT NULL 
- `DoctorOriginationDate` VDT_DATETIME NOT NULL 
- `DoctorTerminationDate` VDT_DATETIME NOT NULL 
- `DoctorInstitution` VDT_NAME NOT NULL 
- `DoctorComment` VDT_COMMENT NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 

**Foreign Keys:**
- `DimLocationID` → `DWH.DimLocation.DimLocationID`
- `DimLookupID_ResourceType` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimDrug
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `DimDrugID` VDT_SERIALNUMBER NOT NULL [PK]
- `UnitOfMeasure` VDT_STRING10 NOT NULL 
- `AgentName` VDT_STRING50 NOT NULL 
- `MedispanDrugName` VDT_STRING30 NOT NULL 
- `PreferredAgentName` VDT_STRING50 NOT NULL 
- `AgentClassDescription` VDT_STRING20 NOT NULL 
- `Route` VDT_STRING2 NOT NULL 
- `Form` VDT_STRING6 NOT NULL 
- `Strength` VDT_STRING15 NOT NULL 
- `ctrdrug_desc_id` VDT_STRING6 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimDxSite
**Columns:** 13 | **Foreign Keys:** 0

**Columns:**
- `DimDxSiteID` VDT_SERIALNUMBER NOT NULL [PK]
- `TpClsTypeId` VDT_INT NOT NULL 
- `TpClsValueId` VDT_INT NOT NULL 
- `SiteDescENU` VDT_STRING254 NOT NULL 
- `SiteDescFRA` VDT_STRING254 NOT NULL 
- `SiteDescESN` VDT_STRING254 NOT NULL 
- `SiteDescCHS` VDT_STRING254 NOT NULL 
- `SiteDescDEU` VDT_STRING254 NOT NULL 
- `SiteDescITA` VDT_STRING254 NOT NULL 
- `SiteDescJPN` VDT_STRING254 NOT NULL 
- `SiteDescPTB` VDT_STRING254 NOT NULL 
- `SiteDescSVE` VDT_STRING254 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimEdiOutMessages
**Columns:** 22 | **Foreign Keys:** 4

**Columns:**
- `DimEdiOutMessagesID` VDT_SERIALNUMBER NOT NULL [PK]
- `TypeOfMessage` VDT_STRING20 NOT NULL 
- `MessageDescription` nvarchar NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimPharmLibID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_MessageOut` VDT_SERIALNUMBER NOT NULL 
- `MessageProcessedIndicator` VDT_STRING1 NOT NULL 
- `MsgSentDate` VDT_DATETIME NOT NULL 
- `DimUserID_MsgEnteredBy_userid` VDT_SERIALNUMBER NOT NULL 
- `MsgEnteredTime` VDT_DATETIME NOT NULL 
- `DimUserID_MsgLastModifiedBy_userid` VDT_SERIALNUMBER NOT NULL 
- `MsgLastModifiedTime` VDT_DATETIME NOT NULL 
- `RefEdiOutID` VDT_INT NOT NULL 
- `MessageUID` VDT_STRING40 NOT NULL 
- `ReqTwoFactorAuth` VDT_STRING1 NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrevent_id` VDT_INT NOT NULL 
- `AdditionalEventId` VDT_INT NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 
- `ctrpharm_id` VDT_STRING20 NOT NULL 
- `ctredi_out_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimPharmLibID` → `DWH.DimPharmacyLibrary.DimPharmLibID`
- `DimUserID_MsgEnteredBy_userid` → `DWH.DimUser.DimUserID`
- `DimUserID_MsgLastModifiedBy_userid` → `DWH.DimUser.DimUserID`

---

### DWH.DimEnergy
**Columns:** 9 | **Foreign Keys:** 1

**Columns:**
- `DimEnergyID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `RadiationType` VDT_ENERGYMODE NOT NULL 
- `Energy` VDT_ENERGY NOT NULL 
- `MaxEnergy` VDT_ENERGY NOT NULL 
- `MinDoseRate` VDT_DOSERATE NOT NULL 
- `MaxDoseRate` VDT_DOSERATE NOT NULL 
- `ctrEnergyModeSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMachineID` → `DWH.DimMachine.DimMachineID`

---

### DWH.DimErxAgt
**Columns:** 35 | **Foreign Keys:** 5

**Columns:**
- `DimErxAgtID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimPharmLibID` VDT_SERIALNUMBER NOT NULL 
- `DimRxAgtID` VDT_SERIALNUMBER NOT NULL 
- `DispensingQuantity` VDT_STRING30 NOT NULL 
- `SentItemIndicator` VDT_STRING1 NOT NULL 
- `ItemNotSentReason` VDT_INT NOT NULL 
- `ItemReceivedIndicator` VDT_STRING1 NOT NULL 
- `ItemReceivedDate` VDT_DATETIME NOT NULL 
- `PrescriptionReferenceNumber` VDT_STRING40 NOT NULL 
- `DimUserID_ErxEnteredBy_userid` VDT_SERIALNUMBER NOT NULL 
- `ErxEnteredTime` VDT_DATETIME NOT NULL 
- `DimUserID_ErxLastModifiedBy_userid` VDT_SERIALNUMBER NOT NULL 
- `ErxLastModifiedTime` VDT_DATETIME NOT NULL 
- `AgentSig` VDT_STRING254 NOT NULL 
- `NotesByPharmacist` nvarchar NOT NULL 
- `ErxRevisionNumber` VDT_INT NOT NULL 
- `ErxSentToPharmacy` VDT_DATETIME NOT NULL 
- `NDCCode` VDT_STRING20 NOT NULL 
- `CourseDescription` VDT_STRING256 NOT NULL 
- `DeaClassFmtCd` VDT_STRING20 NOT NULL 
- `nadean_cd` VDT_STRING20 NOT NULL 
- `epcs_source_rx_id` VDT_INT NOT NULL 
- `epcs_sent_cd` VDT_STRING10 NOT NULL 
- `ghb_reason` nvarchar NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrrx_id` VDT_INT NOT NULL 
- `ctritem_no` VDT_INT NOT NULL 
- `ctrerx_refill_rqst_id` VDT_INT NOT NULL 
- `ctrdest_pharm_id` VDT_STRING20 NOT NULL 
- `ctrstkh_name_id` VDT_INT NOT NULL 
- `ctrerx_agt_rx_id` VDT_INT NOT NULL 
- `DimLookup_ItemNotSentReason` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimPharmLibID` → `DWH.DimPharmacyLibrary.DimPharmLibID`
- `DimRxAgtID` → `DWH.DimRxAgt.DimRxAgtID`
- `DimUserID_ErxEnteredBy_userid` → `DWH.DimUser.DimUserID`
- `DimUserID_ErxLastModifiedBy_userid` → `DWH.DimUser.DimUserID`

---

### DWH.DimErxErrorLog
**Columns:** 16 | **Foreign Keys:** 3

**Columns:**
- `DimErxErrorLogID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimEdiOutMessagesID` VDT_SERIALNUMBER NOT NULL 
- `ExternalErrorCode` VDT_STRING20 NOT NULL 
- `InternalErrorCode` VDT_STRING20 NOT NULL 
- `ErrorDescription` VDT_STRING256 NOT NULL 
- `TechnicalErrorDescription` nvarchar NOT NULL 
- `ReceivedFromSystem` VDT_STRING40 NOT NULL 
- `ErrorGeneratedTime` VDT_DATETIME NOT NULL 
- `ErrorAckInd` VDT_STRING1 NOT NULL 
- `DimUserID_ErrorLogEnteredBy_userid` VDT_SERIALNUMBER NOT NULL 
- `ErrorLogEnteredTime` VDT_DATETIME NOT NULL 
- `DimUserID_ErrorLogModifiedBy_userid` VDT_SERIALNUMBER NOT NULL 
- `ErrorLogModifiedTime` VDT_DATETIME NOT NULL 
- `ctrerx_err_log_id` VDT_INT NOT NULL 
- `ctredi_out_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimEdiOutMessagesID` → `DWH.DimEdiOutMessages.DimEdiOutMessagesID`
- `DimUserID_ErrorLogEnteredBy_userid` → `DWH.DimUser.DimUserID`
- `DimUserID_ErrorLogModifiedBy_userid` → `DWH.DimUser.DimUserID`

---

### DWH.DimField
**Columns:** 44 | **Foreign Keys:** 2

**Columns:**
- `DimFieldID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `RadiationName` VDT_NAME NOT NULL 
- `CollimatorX1` VDT_COLLPARAM NOT NULL 
- `CollimatorX2` VDT_COLLPARAM NOT NULL 
- `CollimatorY1` VDT_COLLPARAM NOT NULL 
- `CollimatorY2` VDT_COLLPARAM NOT NULL 
- `CouchLat` VDT_COUCHPARAM NOT NULL 
- `CouchLng` VDT_COUCHPARAM NOT NULL 
- `CouchVrt` VDT_COUCHPARAM NOT NULL 
- `GantryRtnDirection` VDT_STRING16 NOT NULL 
- `GantryRtnExt` VDT_STRING16 NOT NULL 
- `GantryRotation` VDT_ANGLE NOT NULL 
- `IsoCenterPositionX` VDT_FLOAT NOT NULL 
- `IsoCenterPositionY` VDT_FLOAT NOT NULL 
- `IsoCenterPositionZ` VDT_FLOAT NOT NULL 
- `StopAngle` VDT_ANGLE NOT NULL 
- `FixLightAzimuthAngle` VDT_ANGLE NOT NULL 
- `PatientSupportAngle` VDT_ANGLE NOT NULL 
- `GatingFlag` VDT_INT NOT NULL 
- `SetupFieldFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `LastTreatmentDate` VDT_DATETIME NOT NULL 
- `PrimaryDosimeterUnit` VDT_ID NOT NULL 
- `SetupNote` VDT_STRING254 NOT NULL 
- `SSD` VDT_FLOAT NOT NULL 
- `MURounded` VDT_FLOAT NOT NULL 
- `ToleranceId` VDT_ID NOT NULL 
- `ToleranceTable` VDT_NAME NOT NULL 
- `FixLightPolarPos` VDT_ANGLE NOT NULL 
- `WedgeDose` VDT_DOSE NOT NULL 
- `RefDose` VDT_DOSE NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `CollMode` VDT_COLLMODE NOT NULL 
- `CollRtn` VDT_ANGLE NOT NULL 
- `PlannedTreatmentTime` VDT_TIME NOT NULL 
- `MLCPlanType` VDT_TABLENAME NOT NULL 
- `IndexParameterType` VDT_TYPE NOT NULL 
- `IMRTOrRapidArc` VDT_STRING16 NOT NULL 
- `ctrRadiationSer` VDT_SERIALNUMBER NOT NULL 
- `ctrToleranceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefImageSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPlanID` → `DWH.DimPlan.DimPlanID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`

---

### DWH.DimGroupResources
**Columns:** 7 | **Foreign Keys:** 2

**Columns:**
- `DimGroupResourcesID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimResourceGroupID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `ctrGroupResourceSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimResourceGroupID` → `DWH.DimResourceGroup.DimResourceGroupID`
- `DimResourceID` → `DWH.DimResource.DimResourceID`

---

### DWH.DimHospitalDepartment
**Columns:** 15 | **Foreign Keys:** 0

**Columns:**
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL [PK]
- `HospitalName` VDT_NAME NOT NULL 
- `HospitalLocation` VDT_STRING64 NOT NULL 
- `HospitalCompleteAddress` VDT_STRING512 NOT NULL 
- `HospitalWebAddress` VDT_STRING64 NOT NULL 
- `DepartmentId` VDT_ID NOT NULL 
- `DepartmentName` VDT_NAME NOT NULL 
- `DepartmentComment` VDT_COMMENT NOT NULL 
- `DepartmentHstryDateTime` VDT_DATETIME NOT NULL 
- `HospitalHstryDateTime` VDT_DATETIME NOT NULL 
- `ctrHospitalSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `HospitalTelephoneExtension` VDT_STRING30 NOT NULL 

---

### DWH.DimICDOSite
**Columns:** 23 | **Foreign Keys:** 0

**Columns:**
- `DimICDOSiteID` VDT_SERIALNUMBER NOT NULL [PK]
- `ICDOSiteCodeId` VDT_STRING10 NOT NULL 
- `ICDOSequence` VDT_INT NOT NULL 
- `ICDOClsSchemeId` VDT_INT NOT NULL 
- `ICDOSiteCodeENU` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeFRA` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeESN` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeCHS` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeDEU` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeITA` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeJPN` VDT_STRING254 NOT NULL 
- `ICDOSiteCodePTB` VDT_STRING254 NOT NULL 
- `ICDOSiteCodeSVE` VDT_STRING254 NOT NULL 
- `ICDOVersionENU` VDT_STRING512 NOT NULL 
- `ICDOVersionFRA` VDT_STRING512 NOT NULL 
- `ICDOVersionESN` VDT_STRING512 NOT NULL 
- `ICDOVersionCHS` VDT_STRING512 NOT NULL 
- `ICDOVersionDEU` VDT_STRING512 NOT NULL 
- `ICDOVersionITA` VDT_STRING512 NOT NULL 
- `ICDOVersionJPN` VDT_STRING512 NOT NULL 
- `ICDOVersionPTB` VDT_STRING512 NOT NULL 
- `ICDOVersionSVE` VDT_STRING512 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimInstituteLocation
**Columns:** 22 | **Foreign Keys:** 1

**Columns:**
- `DimInstituteLocationID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `EventType` VDT_STRING80 NOT NULL 
- `LocationDescription` VDT_STRING80 NOT NULL 
- `BuildingName` VDT_STRING60 NOT NULL 
- `FloorName` VDT_STRING60 NOT NULL 
- `RoomName` VDT_STRING60 NOT NULL 
- `DepartmentName` VDT_STRING60 NOT NULL 
- `LocationGroupName` VDT_STRING60 NOT NULL 
- `Capacity` VDT_INT NOT NULL 
- `SlotSize` VDT_INT NOT NULL 
- `LocationOpenTime` VDT_STRING10 NOT NULL 
- `LocationCloseTime` VDT_STRING10 NOT NULL 
- `LocationComment` VDT_STRING512 NOT NULL 
- `LocationTel` VDT_STRING60 NOT NULL 
- `PrimaryInd` VDT_STRING2 NOT NULL 
- `ActiveEntryInd` VDT_STRING2 NOT NULL 
- `ctrloc_id` VDT_INT NOT NULL 
- `ctrbldg_id` VDT_INT NOT NULL 
- `ctrfloor_id` VDT_INT NOT NULL 
- `ctrroom_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimLocation
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `DimLocationID` VDT_SERIALNUMBER NOT NULL [PK]
- `Country` VDT_ADDRESSLINE NOT NULL 
- `State` VDT_ADDRESSLINE NOT NULL 
- `City` VDT_ADDRESSLINE NOT NULL 
- `County` VDT_ADDRESSLINE NOT NULL 
- `PostalCode` VDT_POSTALCODE NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimLookup
**Columns:** 16 | **Foreign Keys:** 0

**Columns:**
- `DimLookupID` VDT_SERIALNUMBER NOT NULL [PK]
- `TableName` VDT_NAME NOT NULL 
- `LookupCode` VDT_STRING64 NOT NULL 
- `LookupType` VDT_INT NOT NULL 
- `SubSelector` VDT_SERIALNUMBER NOT NULL 
- `LookupDescriptionENU` VDT_STRING256 NOT NULL 
- `LookupDescriptionFRA` VDT_STRING256 NOT NULL 
- `LookupDescriptionESN` VDT_STRING256 NOT NULL 
- `LookupDescriptionCHS` VDT_STRING256 NOT NULL 
- `LookupDescriptionDEU` VDT_STRING256 NOT NULL 
- `LookupDescriptionITA` VDT_STRING256 NOT NULL 
- `LookupDescriptionJPN` VDT_STRING256 NOT NULL 
- `LookupDescriptionPTB` VDT_STRING256 NOT NULL 
- `LookupDescriptionSVE` VDT_STRING256 NOT NULL 
- `ctrLookupTableSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimMachine
**Columns:** 25 | **Foreign Keys:** 1

**Columns:**
- `DimMachineID` VDT_SERIALNUMBER NOT NULL [PK]
- `MachineFullName` VDT_STRING128 NOT NULL 
- `MachineAliasName` VDT_NAME NOT NULL 
- `MachineId` VDT_STRING256 NOT NULL 
- `Schedulable` varchar NOT NULL 
- `MachineModel` VDT_STRING64 NOT NULL 
- `MachineScale` VDT_SCALE NOT NULL 
- `MachineType` VDT_TABLENAME NOT NULL 
- `ResourceTypeNum` VDT_NUMBER NOT NULL 
- `ResourceObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RadiationDeviceType` VDT_SERIALNUMBER NOT NULL 
- `MaxDwellTimePerChannel` VDT_FLOAT NOT NULL 
- `MaxDwellTimePerPos` VDT_FLOAT NOT NULL 
- `MaxDwellTimePerTreatment` VDT_FLOAT NOT NULL 
- `TimeResolution` VDT_FLOAT NOT NULL 
- `SourceMovementType` VDT_STRING16 NOT NULL 
- `MinStepSize` VDT_FLOAT NOT NULL 
- `MaxStepSize` VDT_FLOAT NOT NULL 
- `NumOfDwellPosPerChannel` VDT_INT NOT NULL 
- `StepSizeResolution` VDT_FLOAT NOT NULL 
- `PosToSourceDist` VDT_FLOAT NOT NULL 
- `DoseRateMode` VDT_STRING16 NOT NULL 
- `BrachyExportPostProcessor` VDT_STRING254 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimLookupID_RadiationDeviceType` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimMedoncPlan
**Columns:** 17 | **Foreign Keys:** 0

**Columns:**
- `DimMedoncPlanID` VDT_SERIALNUMBER NOT NULL [PK]
- `ctrtp_name` VDT_STRING20 NOT NULL 
- `TreatmentPlanDisplayName` VDT_STRING100 NOT NULL 
- `ctrtp_vers_no` VDT_STRING10 NOT NULL 
- `PlanStatus` VDT_STRING1 NOT NULL 
- `PlanStatusDesc` VDT_STRING15 NOT NULL 
- `PlanType` VDT_INT NOT NULL 
- `PlanTypeDescription` VDT_STRING60 NOT NULL 
- `DimLookupID_Sex` VDT_SERIALNUMBER NOT NULL 
- `StartingAgeOfPatient` VDT_INT NOT NULL 
- `EndingAgeOfPatient` VDT_INT NOT NULL 
- `ClinicalTrialIndicator` VDT_STRING2 NOT NULL 
- `ActiveIndicator` VDT_STRING2 NOT NULL 
- `PlanSummary` VDT_STRING1024 NOT NULL 
- `PlanBriefDesc` VDT_STRING254 NOT NULL 
- `PlanClassification` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimMedoncPlanInterval
**Columns:** 33 | **Foreign Keys:** 2

**Columns:**
- `DimMedoncPlanIntervalID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMedoncPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimMedoncPlanPhaseID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_DosageForm` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AdminDosageUnit` VDT_SERIALNUMBER NOT NULL 
- `ReceipentDisciplineType` VDT_STRING40 NOT NULL 
- `TypeOfTest` VDT_STRING20 NOT NULL 
- `EventType` VDT_STRING1 NOT NULL 
- `EventName` VDT_STRING40 NOT NULL 
- `EventDescription` VDT_STRING100 NOT NULL 
- `PlanInterventionName` VDT_STRING256 NOT NULL 
- `InterventionDetailText` VDT_STRING1024 NOT NULL 
- `PhaseSequenceNumber` VDT_INT NOT NULL 
- `TPCycleNumber` VDT_INT NOT NULL 
- `CycleDay` VDT_INT NOT NULL 
- `CyclicIndicator` VDT_STRING1 NOT NULL 
- `PRNIndicator` VDT_STRING1 NOT NULL 
- `AgentName` VDT_STRING60 NOT NULL 
- `DoseLevelDescription` VDT_STRING40 NOT NULL 
- `AdminDosage` VDT_NUMERIC_11_4 NOT NULL 
- `SpecialInstructions` VDT_STRING1024 NOT NULL 
- `ReminderShortDescription` VDT_STRING60 NOT NULL 
- `ReminderDescription` VDT_STRING1024 NOT NULL 
- `ComponentName` VDT_STRING30 NOT NULL 
- `QuestionnaireName` VDT_STRING20 NOT NULL 
- `GradingSchemeAuthour` VDT_INT NOT NULL 
- `GradingSchemeEffectiveDate` VDT_DATETIME NOT NULL 
- `ToxicityType` VDT_STRING30 NOT NULL 
- `ToxicityComponentName` VDT_STRING30 NOT NULL 
- `ToxicityReason` VDT_STRING1024 NOT NULL 
- `ToxicitySubComponentName` VDT_STRING60 NOT NULL 
- `ctrintv_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMedoncPlanID` → `DWH.DimMedoncPlan.DimMedoncPlanID`
- `DimMedoncPlanPhaseID` → `DWH.DimMedoncPlanPhase.DimMedoncPlanPhaseID`

---

### DWH.DimMedoncPlanPhase
**Columns:** 14 | **Foreign Keys:** 1

**Columns:**
- `DimMedoncPlanPhaseID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMedoncPlanID` VDT_SERIALNUMBER NOT NULL 
- `ctrphase_seq_no` VDT_INT NOT NULL 
- `PhaseDescription` VDT_STRING100 NOT NULL 
- `NumberOfCycles` VDT_INT NOT NULL 
- `AllowableDrift` VDT_INT NOT NULL 
- `AllowableDelay` VDT_INT NOT NULL 
- `TimePeriodDuration` VDT_INT NOT NULL 
- `TimePeriodDurationUnit` VDT_INT NOT NULL 
- `LengthOfCycle` VDT_INT NOT NULL 
- `PhaseBriefDescription` nvarchar NOT NULL 
- `ConsentDescription` nvarchar NOT NULL 
- `RequiredIndicator` VDT_STRING2 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMedoncPlanID` → `DWH.DimMedoncPlan.DimMedoncPlanID`

---

### DWH.DimMedoncPlanSummary
**Columns:** 8 | **Foreign Keys:** 1

**Columns:**
- `DimMedoncPlanSummaryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMedoncPlanID` VDT_SERIALNUMBER NOT NULL 
- `ctrtp_name` VDT_STRING20 NOT NULL 
- `ctrtp_vers_no` VDT_STRING10 NOT NULL 
- `ctrpln_sum_typ` VDT_INT NOT NULL 
- `PlanSummaryTypeDescription` VDT_STRING30 NOT NULL 
- `PlanSummaryDescription` nvarchar NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMedoncPlanID` → `DWH.DimMedoncPlan.DimMedoncPlanID`

---

### DWH.DimNationality
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `DimNationalityID` VDT_SERIALNUMBER NOT NULL [PK]
- `CitizenShip` VDT_STRING64 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimOperatingLimit
**Columns:** 13 | **Foreign Keys:** 1

**Columns:**
- `DimOperatingLimitID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `ParameterType` VDT_TYPE NOT NULL 
- `ParameterName` VDT_NAME NOT NULL 
- `MinValue` VDT_FLOAT NOT NULL 
- `MaxValue` VDT_FLOAT NOT NULL 
- `DefValue` VDT_FLOAT NOT NULL 
- `LimitPrecision` VDT_INT NOT NULL 
- `TolerancePossible` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `MotionMode` VDT_STRING64 NOT NULL 
- `MaxSpeed` VDT_FLOAT NOT NULL 
- `ctrOperatingLimitSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMachineID` → `DWH.DimMachine.DimMachineID`

---

### DWH.DimPatient
**Columns:** 79 | **Foreign Keys:** 0

**Columns:**
- `DimPatientID` VDT_SERIALNUMBER NOT NULL [PK]
- `PatientId` nvarchar NOT NULL 
- `PatientId2` nvarchar NOT NULL 
- `PatientFirstName` nvarchar NOT NULL 
- `PatientLastName` nvarchar NOT NULL 
- `PatientFullName` nvarchar NOT NULL 
- `PatientHonorific` VDT_STRING16 NOT NULL 
- `PatientDateOfBirth` VDT_DATETIME NOT NULL 
- `PatientType` VDT_TABLENAME NOT NULL 
- `PatientSSN` VDT_STRING64 NOT NULL 
- `PatientLanguage` nvarchar NOT NULL 
- `PatientAddressLine1` VDT_ADDRESSLINE NOT NULL 
- `PatientAddressLine2` VDT_ADDRESSLINE NOT NULL 
- `PatientFullAddress` VDT_STRING512 NOT NULL 
- `PatientAddressComment` VDT_COMMENT NOT NULL 
- `PatientHomePhone` VDT_PHONENUMBER NOT NULL 
- `PatientWorkPhone` VDT_PHONENUMBER NOT NULL 
- `PatientMobilePhone` VDT_PHONENUMBER NOT NULL 
- `PatientPagerNumber` VDT_PHONENUMBER NOT NULL 
- `PatientEMailAddress` VDT_STRING64 NOT NULL 
- `PatientLocation` VDT_STRING512 NOT NULL 
- `PatientInOutStatus` VDT_STRING10 NOT NULL 
- `PatientDeathStatus` VDT_STRING10 NOT NULL 
- `PatientDeathCause` VDT_COMMENT NOT NULL 
- `PatientDeathDate` VDT_DATETIME NOT NULL 
- `ClinicalTrial` VDT_STRING10 NOT NULL 
- `PatientComment` VDT_COMMENT NOT NULL 
- `PatientNotes` VDT_STRING1024 NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `PatientRoomNumber` VDT_ID NOT NULL 
- `PatientEmergencyContactAddress` VDT_STRING512 NOT NULL 
- `PatientEmergencyContactComment` VDT_COMMENT NOT NULL 
- `PatientEmergencyContactEntrusted` VDT_NUMBER NOT NULL 
- `PatientEmergencyContactFullName` VDT_STRING256 NOT NULL 
- `PatientEmergencyContactHomePhone` VDT_PHONENUMBER NOT NULL 
- `PatientEmergencyContactMobilePhone` VDT_PHONENUMBER NOT NULL 
- `PatientEmergencyContactWorkPhone` VDT_PHONENUMBER NOT NULL 
- `PatientEmergencyContactRelationship` VDT_STRING64 NOT NULL 
- `TransportationName` VDT_STRING64 NOT NULL 
- `TransportationPhone` VDT_PHONENUMBER NOT NULL 
- `NoAlcoholUsePerWeek` VDT_INT NOT NULL 
- `NoPacksPerDay` numeric NOT NULL 
- `NoYearsQuitAlcohol` VDT_INT NOT NULL 
- `NoYearsQuitSmoking` VDT_INT NOT NULL 
- `NoYearsActiveSmoker` VDT_INT NOT NULL 
- `HazardMaterialContactIndicator` VDT_STRING1 NOT NULL 
- `AlcoholUseStatus` VDT_STRING25 NOT NULL 
- `SmokingUseStatus` VDT_STRING25 NOT NULL 
- `ctrPatientSocialHistoryId` VDT_INT NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrHospitalSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrimaryOncologistSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrimaryReferringPhysicianSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `PatientMiddleName` VDT_NAME NOT NULL 
- `UniversalPatientId` VDT_STRING32 NOT NULL 
- `PatientMaritalStatus` VDT_STRING10 NOT NULL 
- `PatientOccupation` VDT_STRING32 NOT NULL 
- `PatientPresentEmployerName` VDT_STRING32 NOT NULL 
- `MotherName` VDT_STRING32 NOT NULL 
- `FatherName` VDT_STRING32 NOT NULL 
- `Ethnicity` VDT_STRING64 NOT NULL 
- `Religion` VDT_STRING64 NOT NULL 
- `MotherMaidenName` VDT_STRING32 NOT NULL 
- `HealthCaredpoa` VDT_STRING1 NOT NULL 
- `DoNotResuscitate` VDT_STRING1 NOT NULL 
- `DoNotHospitalize` VDT_STRING1 NOT NULL 
- `HasLivingWill` VDT_STRING1 NOT NULL 
- `IsAutopsyRequested` VDT_STRING1 NOT NULL 
- `FeedingRestrictions` VDT_STRING1 NOT NULL 
- `IsOrganDonor` VDT_STRING1 NOT NULL 
- `BirthPlace` VDT_STRING60 NOT NULL 
- `MedicationRestrictions` VDT_STRING1 NOT NULL 
- `TreatmentRestrictions` VDT_STRING1 NOT NULL 
- `IsMOTestPatient` bit NOT NULL 
- `SmokingSinceDate` VDT_DATETIME NOT NULL 
- `SmokingQuitDate` VDT_DATETIME NOT NULL 
- `AlcoholQuitDate` VDT_DATETIME NOT NULL 

---

### DWH.DimPatientAdmissionStatus
**Columns:** 10 | **Foreign Keys:** 2

**Columns:**
- `DimPatientAdmissionStatusID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `PatientHospitalRevCount` VDT_REVISIONCOUNT NOT NULL 
- `PatientDepartmentDefaultFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `StartDateTime` VDT_DATETIME NOT NULL 
- `EndDateTime` VDT_DATETIME NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `InPatientFlag` int NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimPatientDepartment
**Columns:** 9 | **Foreign Keys:** 2

**Columns:**
- `DimPatientDepartmentID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `EffectiveStartDate` VDT_DATETIME NOT NULL 
- `EffectiveEndDate` VDT_DATETIME NOT NULL 
- `DefaultFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ctrPatientDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimPatientDepartmentbyCUID
**Columns:** 8 | **Foreign Keys:** 3

**Columns:**
- `DimPatientDepartmentbyCUIDID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `EffectiveStartDate` VDT_DATETIME NOT NULL 
- `EffectiveEndDate` VDT_DATETIME NOT NULL 
- `ctrPatientDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimUserID` → `DWH.DimUser.DimUserID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimPatientDiseaseResponse
**Columns:** 15 | **Foreign Keys:** 1

**Columns:**
- `DimPatientDiseaseResponseID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AssessmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_EffectiveDate` VDT_SERIALNUMBER NOT NULL 
- `DiseaseStatus` VDT_INT NOT NULL 
- `DiseaseResponse` VDT_STRING1024 NOT NULL 
- `AssessmentDate` VDT_DATETIME NOT NULL 
- `DiseaseStatusEffectiveDate` VDT_DATETIME NOT NULL 
- `DiseaseStatusValidEntryIndicator` VDT_STRING2 NOT NULL 
- `DiagnosisValidEntryIndicator` VDT_STRING2 NOT NULL 
- `ctrpt_tx_id` VDT_INT NOT NULL 
- `ctrcncr_status_id` VDT_INT NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`

---

### DWH.DimPatientDoctor
**Columns:** 22 | **Foreign Keys:** 0

**Columns:**
- `DimPatientDoctorID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `PrimaryFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `OncologistFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrprovider_stkh_id` VDT_STRING20 NOT NULL 
- `ctrorg_stkh_id` VDT_STRING20 NOT NULL 
- `ctrpt_provider_id` VDT_INT NOT NULL 
- `ReferralDate` VDT_DATETIME NOT NULL 
- `ReferralCode` VDT_STRING1 NOT NULL 
- `ProfRelationType` VDT_INT NOT NULL 
- `ProfRelationTypeDesc` VDT_STRING80 NOT NULL 
- `EffectiveStartDate` VDT_DATETIME NOT NULL 
- `EffectiveEndDate` VDT_DATETIME NOT NULL 
- `InternalIndicator` VDT_STRING2 NOT NULL 
- `EndReasonCode` VDT_STRING10 NOT NULL 
- `ActiveEntryIndicator` VDT_STRING2 NOT NULL 
- `ValidEntryIndicator` VDT_STRING2 NOT NULL 
- `MOROIndicator` VDT_STRING10 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimPatientInstituteKey
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `PtInstKeyID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `PtKeyCd` VDT_INT NOT NULL 
- `PtKeyValue` nvarchar NOT NULL 
- `ctrpt_id` nchar NOT NULL 
- `ctrinst_id` nchar NOT NULL 
- `ctrpt_inst_key_id` VDT_INT NOT NULL 
- `CurrentValueIndicator` nchar NOT NULL 
- `ValidEntryIndicator` nchar NOT NULL 
- `InstPtKeyDesc` VDT_STRING40 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimPatientJournal
**Columns:** 15 | **Foreign Keys:** 3

**Columns:**
- `DimPatientJournalID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_Author` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID_Author` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_Journal` VDT_SERIALNUMBER NOT NULL 
- `ApprovedFlag` VDT_SLOTPOS NOT NULL 
- `JournalDate` VDT_DATETIME NOT NULL 
- `JournalText` nvarchar NOT NULL 
- `JournalTypeDescription` VDT_STRING512 NOT NULL 
- `JournalErrorReasonText` VDT_STRING512 NOT NULL 
- `JournalRevisionNumber` VDT_REVISIONCOUNT NOT NULL 
- `JournalValidEntryIndicator` VDT_STRING1 NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrquick_note_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimUserID_Author` → `DWH.DimUser.DimUserID`
- `DimHospitalDepartmentID_Author` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimPatientPerformanceStatus
**Columns:** 25 | **Foreign Keys:** 0

**Columns:**
- `PerformanceStatusID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AssessmentDate` VDT_SERIALNUMBER NOT NULL 
- `PerformanceStatusScale` VDT_INT NOT NULL 
- `DimDateID_PerfStatusEffectiveDate` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisStatusId` VDT_INT NOT NULL 
- `PerformanceStatusValue` VDT_INT NOT NULL 
- `ImpressionDescription` VDT_STRING256 NOT NULL 
- `ApprovedIndicator` VDT_STRING256 NOT NULL 
- `PerformanceStatusDescription` VDT_STRING256 NOT NULL 
- `ValidEntryIndicator` VDT_STRING10 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `TransLogInstId` VDT_STRING30 NOT NULL 
- `TransLogModifiedInstId` VDT_STRING30 NOT NULL 
- `ClassificationValue` VDT_STRING10 NOT NULL 
- `ClassificationSchemeName` VDT_STRING256 NOT NULL 
- `ClassificationSchemeKey` VDT_INT NOT NULL 
- `ActivityRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ApplicationCode` VDT_STRING10 NOT NULL 
- `ErrorReasonText` VDT_STRING256 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimPatientPhoto
**Columns:** 6 | **Foreign Keys:** 1

**Columns:**
- `DimPatientPhotoID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `Picture` VDT_IMAGE_JPEG NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPhotoSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.DimPatientUserDefinedLabels
**Columns:** 35 | **Foreign Keys:** 17

**Columns:**
- `DimPatientUserDefinedLabelsID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable1` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable2` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable3` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable4` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable5` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable6` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable7` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable8` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable9` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable10` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable11` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable12` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable13` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable14` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable15` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UDFLable16` VDT_SERIALNUMBER NOT NULL 
- `UDFValue1` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue2` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue3` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue4` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue5` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue6` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue7` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue8` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue9` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue10` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue11` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue12` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue13` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue14` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue15` VDT_USERDEFATTRIB NOT NULL 
- `UDFValue16` VDT_USERDEFATTRIB NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_UDFLable1` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable2` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable3` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable4` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable5` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable6` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable7` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable8` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable9` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable10` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable11` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable12` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable13` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable14` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable15` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_UDFLable16` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimPatientVisitTracking
**Columns:** 15 | **Foreign Keys:** 3

**Columns:**
- `DimPatientVisitTrackingID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `VisitTrackingDateTime` VDT_DATETIME NOT NULL 
- `VisitTrackingType` VDT_INT NOT NULL 
- `VisitTrackingSeq` VDT_INT NOT NULL 
- `VisitTrackingTypeDesc` VDT_STRING30 NOT NULL 
- `VisitTrackingAbrv` VDT_STRING2 NOT NULL 
- `ValidEntryInd` VDT_STRING2 NOT NULL 
- `ctrpt_id` VDT_STRING30 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrpt_visit_tracking_id` VDT_INT NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimPayor
**Columns:** 21 | **Foreign Keys:** 1

**Columns:**
- `DimPayorID` VDT_SERIALNUMBER NOT NULL [PK]
- `PayorCompanyName` VDT_NAME NOT NULL 
- `PayorPhone` VDT_PHONENUMBER NOT NULL 
- `PayorAddress` VDT_STRING256 NOT NULL 
- `PayorPlanType` VDT_TYPE NOT NULL 
- `PayorPlanExpiraryDate` VDT_DATETIMESTAMP NOT NULL 
- `PayorPlanNumber` VDT_ID NOT NULL 
- `EffectiveDate` VDT_DATETIME NOT NULL 
- `AuthorizedBy` VDT_NAME NOT NULL 
- `AuthorizationPhone` VDT_PHONENUMBER NOT NULL 
- `AuthorizationFAX` VDT_PHONENUMBER NOT NULL 
- `ctrPayorSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlanTypeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPayorAuthorizationSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `InsuranceCompanyParentOrganization` VDT_STRING50 NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `ctrins_co_id` VDT_INT NOT NULL 
- `ctrins_co_parent_id` VDT_INT NOT NULL 
- `MOROIndicator` VDT_STRING2 NOT NULL 

**Foreign Keys:**
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimPharmacyLibrary
**Columns:** 65 | **Foreign Keys:** 0

**Columns:**
- `DimPharmLibID` VDT_SERIALNUMBER NOT NULL [PK]
- `PharmacyUniqueIdentifier` VDT_STRING40 NOT NULL 
- `PharmacyStoreNumber` VDT_STRING40 NOT NULL 
- `RefNo1` VDT_STRING40 NOT NULL 
- `RefNoEqual` VDT_STRING10 NOT NULL 
- `PharmacyStoreName` VDT_STRING100 NOT NULL 
- `PharmacyAddress1` VDT_STRING40 NOT NULL 
- `PharmacyAddress2` VDT_STRING40 NOT NULL 
- `CityOfPharmacy` VDT_STRING40 NOT NULL 
- `StateOfPharmacy` VDT_STRING2 NOT NULL 
- `ZipCodeOfPharmacy` VDT_STRING20 NOT NULL 
- `PrimaryPhoneNoOfPharmacy` VDT_STRING40 NOT NULL 
- `FaxOfPharmacy` VDT_STRING40 NOT NULL 
- `EmailOfPharmacy` VDT_STRING256 NOT NULL 
- `AlternatePhoneOfPharmacy` VDT_STRING25 NOT NULL 
- `TypeOfPhoneNo1` VDT_STRING11 NOT NULL 
- `AlternatePhoneOfPharmacy2` VDT_STRING25 NOT NULL 
- `TypeOfPhoneNo2` VDT_STRING11 NOT NULL 
- `AlternatePhoneOfPharmacy3` VDT_STRING25 NOT NULL 
- `TypeOfPhoneNo3` VDT_STRING11 NOT NULL 
- `AlternatePhoneOfPharmacy4` VDT_STRING25 NOT NULL 
- `TypeOfPhoneNo4` VDT_STRING11 NOT NULL 
- `AlternatePhoneOfPharmacy5` VDT_STRING25 NOT NULL 
- `TypeOfPhoneNo5` VDT_STRING11 NOT NULL 
- `PharmacyActiveDate` VDT_DATETIME NOT NULL 
- `PharmacyInActiveDate` VDT_DATETIME NOT NULL 
- `ErxCode` VDT_INT NOT NULL 
- `AccountNameOfPharmacy` VDT_STRING40 NOT NULL 
- `LastModifiedDateForPharmacy` VDT_STRING25 NOT NULL 
- `IndPharmacyOpenFor24Hrs` VDT_STRING1 NOT NULL 
- `CrossStreetForPharmacy` VDT_STRING40 NOT NULL 
- `ErxServiceByPharmacy` nvarchar NOT NULL 
- `TxtServiceLevelofPharmacy` nvarchar NOT NULL 
- `TxtServiceLevelChangeofPharmacy` nvarchar NOT NULL 
- `VersionNo` VDT_STRING25 NOT NULL 
- `NPINoForPharmacy` VDT_STRING40 NOT NULL 
- `ActiveEntryIndicator` VDT_STRING1 NOT NULL 
- `PharmacyStoreNameInUpper` VDT_STRING100 NOT NULL 
- `PharmacyAddress1Upper` VDT_STRING40 NOT NULL 
- `CityOFPharmacyUpper` VDT_STRING40 NOT NULL 
- `PharmacyType` VDT_STRING1 NOT NULL 
- `PharmacySpecCD` VDT_INT NOT NULL 
- `replace_ncpdpid` VDT_STRING40 NOT NULL 
- `state_license_no` VDT_STRING40 NOT NULL 
- `upin` VDT_STRING40 NOT NULL 
- `FacilityId` VDT_STRING40 NOT NULL 
- `MedicareNo` VDT_STRING40 NOT NULL 
- `MedicaidNo` VDT_STRING40 NOT NULL 
- `payer_id` VDT_STRING40 NOT NULL 
- `dea_no` VDT_STRING40 NOT NULL 
- `hin` VDT_STRING40 NOT NULL 
- `MutuallyDefined` VDT_STRING40 NOT NULL 
- `OrganizationType` VDT_STRING40 NOT NULL 
- `OrganizationId` VDT_STRING20 NOT NULL 
- `parent_org_id` VDT_STRING20 NOT NULL 
- `Latitude` VDT_STRING20 NOT NULL 
- `Longitude` VDT_STRING20 NOT NULL 
- `Precise` VDT_STRING1 NOT NULL 
- `Usecase` VDT_STRING254 NOT NULL 
- `PharmPhoneDescription` VDT_STRING10 NOT NULL 
- `PharmPhoneNumber` VDT_STRING25 NOT NULL 
- `Extension` VDT_STRING10 NOT NULL 
- `Mobile` VDT_STRING1 NOT NULL 
- `Qual` VDT_STRING2 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimPlan
**Columns:** 55 | **Foreign Keys:** 1

**Columns:**
- `DimPlanID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_PlanStatus` VDT_SERIALNUMBER NOT NULL 
- `PlanUID` VDT_UID NOT NULL 
- `NoFractions` VDT_COUNT NOT NULL 
- `TreatmentOrder` VDT_ORDER NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `PlanSetupName` VDT_NAME NOT NULL 
- `TreatmentOrientation` VDT_STRING16 NOT NULL 
- `TreatmentTechnique` VDT_STRING16 NOT NULL 
- `VolumeId` VDT_ID NOT NULL 
- `PrimaryRefPointId` VDT_ID NOT NULL 
- `PrimaryRefPointDelivered` VDT_FLOAT NOT NULL 
- `PrimaryRefPointPlanned` VDT_FLOAT NOT NULL 
- `PrimaryRefPointRemaining` VDT_FLOAT NOT NULL 
- `PrimaryRefPointDeliveredSum` VDT_FLOAT NOT NULL 
- `PrimaryRefPointPlannedSum` VDT_FLOAT NOT NULL 
- `PrimaryRefPointRemainingSum` VDT_FLOAT NOT NULL 
- `NoFractionsPlanned` VDT_INT NOT NULL 
- `NoFractionsRemaining` VDT_INT NOT NULL 
- `NoFractionsTreated` VDT_INT NOT NULL 
- `NoFractionsPlannedSum` VDT_INT NOT NULL 
- `NoFractionsRemainingSum` VDT_INT NOT NULL 
- `NoFractionsTreatedSum` VDT_INT NOT NULL 
- `NoSessionRemaining` VDT_INT NOT NULL 
- `EnergyMode` VDT_STRING1024 NOT NULL 
- `FractionId` VDT_ID NOT NULL 
- `StartDelay` VDT_INT NOT NULL 
- `FractionPatternDigitsPerDay` VDT_INT NOT NULL 
- `FractionPattern` VDT_STRING64 NOT NULL 
- `PredecessorID` VDT_ID NOT NULL 
- `PlanRevision` VDT_INT NOT NULL 
- `NoSessionPlanned` VDT_INT NOT NULL 
- `PlanComment` VDT_COMMENT NOT NULL 
- `PlanIntent` VDT_STRING16 NOT NULL 
- `Age` VDT_INT NOT NULL 
- `RelationshipType` VDT_STRING16 NOT NULL 
- `RelatedPlanUID` VDT_UID NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `CreationDate` VDT_DATETIMESTAMP NOT NULL 
- `FirstDayOfTreatment` VDT_DATETIME NOT NULL 
- `LastDayOfTreatment` VDT_DATETIME NOT NULL 
- `IMRTOrRapidArc` VDT_STRING16 NOT NULL 
- `ctrPlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRelatedRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlanSOPClassSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRelatedPlanSOPClassSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlanRelationshipSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrimaryRefPointSer` VDT_SERIALNUMBER NOT NULL 
- `ctrFirstRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RTTreatmentTechnique` VDT_STRING256 NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `TreatmentType` VDT_TREATMENTTYPE NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimCourseID` → `DWH.DimCourse.DimCourseID`

---

### DWH.DimPlanStatusHistory
**Columns:** 11 | **Foreign Keys:** 1

**Columns:**
- `DimPlanStatusHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_PlanStatusHstryText` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_StatusUserName` VDT_SERIALNUMBER NOT NULL 
- `StatusDateTime` VDT_DATETIME NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ctrPlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrApprovalSer` VDT_SERIALNUMBER NOT NULL 
- `ctrApprovalRevCount` VDT_REVISIONCOUNT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPlanID` → `DWH.DimPlan.DimPlanID`

---

### DWH.DimPrescription
**Columns:** 26 | **Foreign Keys:** 0

**Columns:**
- `DimPrescriptionID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPredecessorPrescriptionID` VDT_SERIALNUMBER NOT NULL 
- `PrescriptionName` VDT_STRING64 NOT NULL 
- `Status` VDT_STRING64 NOT NULL 
- `Revision` VDT_STRING64 NOT NULL 
- `Site` VDT_STRING64 NOT NULL 
- `CreationDate` VDT_DATETIMESTAMP NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `NumberOfFractions` VDT_INT NOT NULL 
- `Technique` VDT_STRING256 NOT NULL 
- `Notes` VDT_STRING1024 NOT NULL 
- `TimeGapType` VDT_STRING32 NOT NULL 
- `PhaseGapNumberOfDays` VDT_INT NOT NULL 
- `PhaseType` VDT_STRING32 NOT NULL 
- `Gating` VDT_STRING32 NOT NULL 
- `BolusFrequency` VDT_STRING256 NOT NULL 
- `BolusThickness` VDT_STRING256 NOT NULL 
- `SimulationNeeded` VDT_FLAG NOT NULL 
- `ApprovedOn` VDT_DATETIMESTAMP NOT NULL 
- `History` VDT_STRING1024 NOT NULL 
- `LinkedPlans` VDT_STRING256 NOT NULL 
- `RelPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPredecessorPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimPrescriptionAnatomy
**Columns:** 14 | **Foreign Keys:** 0

**Columns:**
- `DimPrescriptionAnatomyID` VDT_SERIALNUMBER NOT NULL [PK]
- `AnatomyRole` VDT_ENUM NOT NULL 
- `AnatomyName` VDT_STRING256 NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `ItemType` VDT_STRING64 NOT NULL 
- `ItemValue` VDT_STRING64 NOT NULL 
- `ItemValueUnit` VDT_STRING16 NOT NULL 
- `Param1Value` VDT_STRING64 NOT NULL 
- `Param1ValueUnit` VDT_STRING16 NOT NULL 
- `ctrPrescriptionAnatomySer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionAnatomyItemSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimPrescriptionProperty
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `DimPrescriptionPropertyID` VDT_SERIALNUMBER NOT NULL [PK]
- `PropertyType` VDT_ENUM NOT NULL 
- `PropertyValue` VDT_STRING64 NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `ItemType` VDT_ENUM NOT NULL 
- `ItemValue` VDT_STRING64 NOT NULL 
- `ctrPrescriptionPropertySer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionPropertyItemSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimProcedureCode
**Columns:** 21 | **Foreign Keys:** 0

**Columns:**
- `DimProcedureCodeID` VDT_SERIALNUMBER NOT NULL [PK]
- `ProcedureCode` VDT_STRING64 NOT NULL 
- `ProcedureCodeType` VDT_TYPE NOT NULL 
- `ProcedureCodeDescription` VDT_COMMENT NOT NULL 
- `Description` VDT_STRING64 NOT NULL 
- `ProcedureBillingCode` VDT_ACTIVITYCODE NOT NULL 
- `Complexity` VDT_CODEVALUE NOT NULL 
- `ProcedureCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `Exportable` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `ctrProcedureCodeSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `BillingCodeEffectiveDate` VDT_DATETIME NOT NULL 
- `BillingCodeEstCost` VDT_MONEY NOT NULL 
- `BillingCodeBillPrice` VDT_MONEY NOT NULL 
- `BillingCodeType` VDT_STRING20 NOT NULL 
- `ActiveInd` VDT_STRING1 NOT NULL 
- `ChangeDate` VDT_DATETIME NOT NULL 
- `DimDateID_ChangeDate` VDT_SERIALNUMBER NOT NULL 
- `FacilityBillCode` VDT_STRING60 NOT NULL 
- `DimLookupID_ProcCodeObjectStatus` VDT_SERIALNUMBER NOT NULL 
- `MOROIndicator` VDT_STRING10 NOT NULL 

---

### DWH.DimQuestionnaires
**Columns:** 12 | **Foreign Keys:** 2

**Columns:**
- `DimQuestionnairesID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimLookupID_QuestionType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_QuestionnaireType` VDT_SERIALNUMBER NOT NULL 
- `QuestionnaireTitle` VDT_STRING50 NOT NULL 
- `QuestionnaireStatus` VDT_STRING1 NOT NULL 
- `QuestionNumber` VDT_STRING10 NOT NULL 
- `QuestionTag` VDT_STRING40 NOT NULL 
- `QuestionText` nvarchar NOT NULL 
- `ctrqstr_name` VDT_STRING20 NOT NULL 
- `ctrQuestionId` VDT_INT NOT NULL 
- `QuestionnairesType` VDT_STRING40 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimLookupID_QuestionType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_QuestionnaireType` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimRadioactiveModelSource
**Columns:** 36 | **Foreign Keys:** 7

**Columns:**
- `DimRadioactiveModelSourceID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `RadioactiveSourceId` VDT_ID NOT NULL 
- `RadioactiveSourceName` VDT_NAME NOT NULL 
- `SourceNumber` VDT_NUMBER NOT NULL 
- `SourceSerialNo` VDT_MANUFACTSERIALNO NOT NULL 
- `SourceStrength` VDT_FLOAT NOT NULL 
- `CalibrationDate` VDT_DATETIME NOT NULL 
- `RadioactiveSourceComment` VDT_COMMENT NOT NULL 
- `DimLookupID_RadioactiveSourceObjectStatus` VDT_SERIALNUMBER NOT NULL 
- `RadioactiveSourceModelId` VDT_ID NOT NULL 
- `RadioactiveSourceModelName` VDT_NAME NOT NULL 
- `RadioIsotopType` VDT_STRING64 NOT NULL 
- `HalfTime` VDT_FLOAT NOT NULL 
- `ManufacturerName` VDT_STRING64 NOT NULL 
- `DimLookupID_SourceType` VDT_SERIALNUMBER NOT NULL 
- `ActivityConversionFact` VDT_FLOAT NOT NULL 
- `DoseRateConstant` VDT_FLOAT NOT NULL 
- `ActiveSize` VDT_TRIPLEFLOAT NOT NULL 
- `TotalSize` VDT_TRIPLEFLOAT NOT NULL 
- `DimLookupID_DoseCalcModel` VDT_SERIALNUMBER NOT NULL 
- `RadDoseFunctionType` VDT_STRING32 NOT NULL 
- `RadDoseFunctionNoOfValues` VDT_INT NOT NULL 
- `RadDoseFunctionValuesX` VDT_FLOAT30 NOT NULL 
- `RadDoseFunctionValuesY` VDT_FLOAT30 NOT NULL 
- `RadioactiveSourceModelComment` VDT_COMMENT NOT NULL 
- `LiteratureReference` VDT_STRING1024 NOT NULL 
- `DimLookupID_RadioactiveSourceModelStatus` VDT_SERIALNUMBER NOT NULL 
- `RadioactiveSourceModelStatusDate` VDT_DATETIME NOT NULL 
- `RadioactiveSourceDimUserID` VDT_SERIALNUMBER NOT NULL 
- `RadioactiveSourceHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `RadioactiveSourceModelDimUserID` VDT_SERIALNUMBER NOT NULL 
- `RadioactiveSourceModelHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ctrRadioactiveSourceModelSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRadioactiveSourceSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimMachineID` → `DWH.DimMachine.DimMachineID`
- `DimLookupID_RadioactiveSourceObjectStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_SourceType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_DoseCalcModel` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_RadioactiveSourceModelStatus` → `DWH.DimLookup.DimLookupID`
- `RadioactiveSourceDimUserID` → `DWH.DimUser.DimUserID`
- `RadioactiveSourceModelDimUserID` → `DWH.DimUser.DimUserID`

---

### DWH.DimResource
**Columns:** 6 | **Foreign Keys:** 1

**Columns:**
- `DimResourceID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimLookupID_ResourceType` VDT_SERIALNUMBER NOT NULL 
- `ActualResourceID` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 

**Foreign Keys:**
- `DimLookupID_ResourceType` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimResourceDepartmentHospital
**Columns:** 8 | **Foreign Keys:** 1

**Columns:**
- `DimResourceDepartmentHospitalID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID` VDT_SERIALNUMBER NOT NULL 
- `DefaultDepartmentName` VDT_NAME NOT NULL 
- `AssignedToDepartment` varchar NOT NULL 
- `AccessRights` VDT_STRING32 NOT NULL 
- `ctrResourceDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimResourceID` → `DWH.DimResource.DimResourceID`

---

### DWH.DimResourceGroup
**Columns:** 15 | **Foreign Keys:** 3

**Columns:**
- `DimResourceGroupID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `ResourceGroupCode` VDT_STRING64 NOT NULL 
- `DimLookupID_ResourceGroupCode` VDT_SERIALNUMBER NOT NULL 
- `GroupType` VDT_TYPE NOT NULL 
- `DimLookupID_GroupType` VDT_SERIALNUMBER NOT NULL 
- `DerivedFromResourceGroupSer` VDT_SERIALNUMBER NOT NULL 
- `ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `DimLookupID_ObjectStatus` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `WorklistType` VDT_STRING64 NOT NULL 
- `ctrResourceGroupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimLookupID_ResourceGroupCode` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ObjectStatus` → `DWH.DimLookup.DimLookupID`

---

### DWH.DimRx
**Columns:** 52 | **Foreign Keys:** 2

**Columns:**
- `DimRxID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrrx_id` VDT_INT NOT NULL 
- `RxStatus` VDT_STRING1 NOT NULL 
- `RxDateID` VDT_SERIALNUMBER NOT NULL 
- `RxPharmacy` VDT_INT NOT NULL 
- `RxType_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `CopiesPrinted` VDT_INT NOT NULL 
- `RxComment` VDT_STRING1024 NOT NULL 
- `RxPhysicianOrderId` VDT_INT NOT NULL 
- `RxEnteredBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxEnteredTime` VDT_DATETIME NOT NULL 
- `RxLastModifiedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxLastModifiedTime` VDT_DATETIME NOT NULL 
- `RxOrderedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxValidEntry` VDT_STRING1 NOT NULL 
- `RxInternalPrints` VDT_INT NOT NULL 
- `RxPickupInternalPrints` VDT_INT NOT NULL 
- `RxPickupExternalPrints` VDT_INT NOT NULL 
- `RxApprovedTimeID` VDT_SERIALNUMBER NOT NULL 
- `RxTpName` VDT_STRING20 NOT NULL 
- `RxTpVersion` VDT_STRING10 NOT NULL 
- `RxTpPhase` VDT_INT NOT NULL 
- `RxCycleNO` VDT_INT NOT NULL 
- `RxCycleDay` VDT_INT NOT NULL 
- `RxInteractionCheckingIndicator` VDT_STRING1 NOT NULL 
- `RxPlacerOrderNo` VDT_STRING20 NOT NULL 
- `RxCompletedIndicator` VDT_STRING1 NOT NULL 
- `RxBillAccount` VDT_INT NOT NULL 
- `RxDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxApprovedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxTreatmentStartDateID` VDT_SERIALNUMBER NOT NULL 
- `RxNotDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxReOrderCommentIndicator` VDT_STRING1 NOT NULL 
- `RxReorderReviewIndicator` VDT_STRING1 NOT NULL 
- `RxPromptTreatmentStartDateIndicator` VDT_STRING1 NOT NULL 
- `RxNoCycles` VDT_INT NOT NULL 
- `RxLineOfTreatment` VDT_INT NOT NULL 
- `RxCalculationAuditDescription` VDT_STRING1024 NOT NULL 
- `RxTreatmentIntent_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxTreatmentUse_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxPharmacyApprovedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxPharmacyApprovedTimeID` VDT_SERIALNUMBER NOT NULL 
- `RxPrintedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxErrorReason` VDT_STRING256 NOT NULL 
- `RxSupervisingPhysician_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `RxDateTime` VDT_DATETIME NOT NULL 
- `RxApprovedTime` VDT_DATETIME NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`

---

### DWH.DimRxAdmin
**Columns:** 47 | **Foreign Keys:** 1

**Columns:**
- `DimRxAdminID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimRxAgtID` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrRxAdminId` VDT_INT NOT NULL 
- `RxAdminSequenceNo` VDT_INT NOT NULL 
- `RxAdminAgentName` VDT_STRING50 NOT NULL 
- `RxAdminDosageForm_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDoseLevel_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDatetimeAdministeredID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgentSequenceNo` VDT_INT NOT NULL 
- `RxAdminAsAdvised` VDT_STRING1 NOT NULL 
- `RxAdminDose` decimal NOT NULL 
- `RxAdminDoseApproved` VDT_STRING1 NOT NULL 
- `RxAdminHowRecorded_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminNoDosesTaken` decimal NOT NULL 
- `RxAdminExpectedDateTimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminEnteredBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminEnteredDatetime` VDT_DATETIME NOT NULL 
- `RxAdminLastModifiedby_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminLastModifiedDatetime` VDT_DATETIME NOT NULL 
- `RxAdminAdminRoute_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAdminRouteUnit_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminValidEntry` VDT_STRING1 NOT NULL 
- `RxAdminCourseAdjustIndicator` VDT_STRING1 NOT NULL 
- `RxAdminStopDatetimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminVarianceIndicator` VDT_STRING1 NOT NULL 
- `RxAdminErrorReason` VDT_STRING256 NOT NULL 
- `RxAdminDispenseVerifiedDatetimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxAdminCourseDescription` VDT_STRING256 NOT NULL 
- `RxAdminCorrected` VDT_STRING1 NOT NULL 
- `RxAdminAdhocEntry` VDT_STRING1 NOT NULL 
- `RxAdminNotDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxAdminDispensingLocation` VDT_INT NOT NULL 
- `RxAdminCycleNo` VDT_INT NOT NULL 
- `RxAdminCycleDay` VDT_INT NOT NULL 
- `RxAdminWastage` numeric NOT NULL 
- `RxAdminWastageUnit_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminRevisionNo` VDT_INT NOT NULL 
- `RxAdminDrugLotNo` VDT_STRING30 NOT NULL 
- `RxAdminManufacturer` VDT_INT NOT NULL 
- `RxAdminDisclosedFlag` VDT_STRING1 NOT NULL 
- `RxAdminRefusedIndicator` VDT_STRING1 NOT NULL 
- `RxAdminExpiryDateID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminStatus` VDT_STRING30 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimRxAgtID` → `DWH.DimRxAgt.DimRxAgtID`

---

### DWH.DimRxAgt
**Columns:** 99 | **Foreign Keys:** 2

**Columns:**
- `DimRxAgtID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimRxID` VDT_SERIALNUMBER NOT NULL 
- `DimRxHydraID` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrrx_id` VDT_INT NOT NULL 
- `ctrRxAgtItemNo` VDT_INT NOT NULL 
- `RxAgtAgentName` VDT_STRING50 NOT NULL 
- `DimLookupID_RxAgtDosageForm` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxAgtDoseLevel` VDT_SERIALNUMBER NOT NULL 
- `RxAgtRxDose` numeric NOT NULL 
- `RxAgtRxTotal` numeric NOT NULL 
- `DimLookupID_RxAgtDosageUnit` VDT_SERIALNUMBER NOT NULL 
- `RxAdminRoute` VDT_INT NOT NULL 
- `DimLookupID_RxDoseFrequencyUnit` VDT_SERIALNUMBER NOT NULL 
- `RxAdminFrequency` VDT_INT NOT NULL 
- `DimLookupID_RxAdminFrequencyUnit` VDT_SERIALNUMBER NOT NULL 
- `RxDuration` VDT_INT NOT NULL 
- `DimLookupID_RxDurationUnit` VDT_SERIALNUMBER NOT NULL 
- `RxRequired` VDT_STRING1 NOT NULL 
- `RxAgtStatus` VDT_STRING1 NOT NULL 
- `RxSubstitutionsAllowed` VDT_STRING1 NOT NULL 
- `RxDiscontinueDateID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminStartDateID` VDT_SERIALNUMBER NOT NULL 
- `RxSubstitutionReason` nvarchar NOT NULL 
- `RxDiscontinueReason` nvarchar NOT NULL 
- `RxDiscontinueEffectiveDateID` VDT_SERIALNUMBER NOT NULL 
- `RxPrnIndicator` VDT_STRING1 NOT NULL 
- `RxPrnRepeatIndicator` VDT_STRING1 NOT NULL 
- `RxDoseRange` numeric NOT NULL 
- `RxStrength` numeric NOT NULL 
- `DimLookupID_RxStrengthUnit` VDT_SERIALNUMBER NOT NULL 
- `RxTpInitDateID` VDT_SERIALNUMBER NOT NULL 
- `RxDispenseQuantity` numeric NOT NULL 
- `RxCourseDescription` VDT_STRING256 NOT NULL 
- `DimLookupID_RxDayofWeekFrequencyUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxWeekFrequencyUnit` VDT_SERIALNUMBER NOT NULL 
- `RxPlacerOrderNo` VDT_STRING30 NOT NULL 
- `DimLookupID_RxOrderUnit` VDT_SERIALNUMBER NOT NULL 
- `RxOrderDose` numeric NOT NULL 
- `RxAgtSequenceNo` VDT_INT NOT NULL 
- `DimLookupID_RxInfusionType` VDT_SERIALNUMBER NOT NULL 
- `RxInfusionDuration` VDT_INT NOT NULL 
- `DimLookupID_RxInfusionTimescale` VDT_SERIALNUMBER NOT NULL 
- `RxAgtValidEntryInd` VDT_STRING1 NOT NULL 
- `DimLookupID_RxPrnReason` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxAgtRxType` VDT_SERIALNUMBER NOT NULL 
- `RxRefillIndicator` VDT_STRING1 NOT NULL 
- `RxRefillQuantity` VDT_INT NOT NULL 
- `RxDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxDoseStrength` VDT_STRING15 NOT NULL 
- `RxAgentVolume` numeric NOT NULL 
- `DimLookupID_RxAgentVolumeUnit` VDT_SERIALNUMBER NOT NULL 
- `RxDispenseDoseLevelIndicator` VDT_STRING1 NOT NULL 
- `RxDoseRecordIndicator` VDT_STRING1 NOT NULL 
- `RxAgtInactivateIndicator` VDT_STRING1 NOT NULL 
- `DimUserID_RxAgtRxEnteredBy` VDT_SERIALNUMBER NOT NULL 
- `RxAgtRxEnteredTime` VDT_DATETIME NOT NULL 
- `DimUserID_RxAgtLastModifiedBy` VDT_SERIALNUMBER NOT NULL 
- `RxAgtLastModifiedTime` VDT_DATETIME NOT NULL 
- `RxAgtDosePercent` numeric NOT NULL 
- `RxAgtChangeIndicator` VDT_STRING1 NOT NULL 
- `RxAdhocActiveEntry` VDT_STRING1 NOT NULL 
- `RxAgtCycleNo` VDT_INT NOT NULL 
- `RxAgtCycleDay` VDT_INT NOT NULL 
- `RxAgtTakeAsDirected` VDT_STRING1 NOT NULL 
- `RxDispenseVolume` numeric NOT NULL 
- `DimLookupID_RxDispenseUnit` VDT_SERIALNUMBER NOT NULL 
- `RxAdminFrequencyUpper` VDT_INT NOT NULL 
- `RxAgtNotDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxDispenseLocation` VDT_INT NOT NULL 
- `RxOverrideDoseTimesIndicator` VDT_STRING1 NOT NULL 
- `RxSynchronizeDoseTimesIndicator` VDT_STRING1 NOT NULL 
- `RxReviewRequiredIndicator` VDT_STRING1 NOT NULL 
- `RxContinueRxIndicator` VDT_STRING1 NOT NULL 
- `RxAdminDoseChange` VDT_STRING1 NOT NULL 
- `RxAdminDosesRecorded` VDT_INT NOT NULL 
- `RxAdminDoseTotal` VDT_INT NOT NULL 
- `RxDosesonHold` VDT_INT NOT NULL 
- `RxApp_cd` VDT_STRING10 NOT NULL 
- `RxTpName` VDT_STRING20 NOT NULL 
- `RxTpVersion` VDT_STRING10 NOT NULL 
- `RxTpPhase` VDT_INT NOT NULL 
- `RxReason` VDT_STRING256 NOT NULL 
- `RxHydrationOverrideComment` VDT_STRING256 NOT NULL 
- `DimUserID_RxHydrationOverriddenBy` VDT_SERIALNUMBER NOT NULL 
- `RxHydrationOverrideDatetimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAgentLevelStatus` VDT_STRING1 NOT NULL 
- `RxAgentDisplayOrder` VDT_INT NOT NULL 
- `RxConcentration` VDT_STRING15 NOT NULL 
- `RxImmunizationCode` VDT_STRING30 NOT NULL 
- `RxImmunizationPresentedDateID` VDT_SERIALNUMBER NOT NULL 
- `RxImmunizationPublishedDateID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_RxImmunizationEnteredBy` VDT_SERIALNUMBER NOT NULL 
- `RxImmunizationEnteredDatetime` VDT_DATETIME NOT NULL 
- `DimUserID_RxImmunizationLastModifiedBy` VDT_SERIALNUMBER NOT NULL 
- `RxImmunizationLastModifiedDatetime` VDT_DATETIME NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `GeneralOrders` nvarchar NOT NULL 

**Foreign Keys:**
- `DimRxID` → `DWH.DimRx.DimRxID`
- `DimRxHydraID` → `DWH.DimRxHydra.DimRxHydraID`

---

### DWH.DimRxHydra
**Columns:** 17 | **Foreign Keys:** 1

**Columns:**
- `DimRxHydraID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimRxID` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrrx_id` VDT_INT NOT NULL 
- `ctrr_hydra_id` VDT_INT NOT NULL 
- `RxHydraFluidId` VDT_INT NOT NULL 
- `RxHydraVolume` numeric NOT NULL 
- `RxHydraVolumeUnit_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxHydraDescription` VDT_STRING256 NOT NULL 
- `RxHydraSequence` VDT_INT NOT NULL 
- `RxHydraInfusionLine` VDT_INT NOT NULL 
- `RxHydraOrderVolume` numeric NOT NULL 
- `RxHydraOrderVolumeUnit_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxHydraTotalBagVolume` numeric NOT NULL 
- `RxHydraCalculationType` VDT_STRING2 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimRxID` → `DWH.DimRx.DimRxID`

---

### DWH.DimStaff
**Columns:** 28 | **Foreign Keys:** 0

**Columns:**
- `DimStaffID` VDT_SERIALNUMBER NOT NULL [PK]
- `StaffFirstName` VDT_NAME NOT NULL 
- `StaffLastName` VDT_NAME NOT NULL 
- `StaffFullName` VDT_STRING256 NOT NULL 
- `StaffAliasName` VDT_NAME NOT NULL 
- `StaffHonorific` VDT_STRING16 NOT NULL 
- `StaffNameSuffix` VDT_NAMESUFFIX NOT NULL 
- `StaffId` VDT_STRING256 NOT NULL 
- `ResourceTypeNum` VDT_NUMBER NOT NULL 
- `StaffObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `Schedulable` varchar NOT NULL 
- `StaffCompleteAddress` VDT_STRING512 NOT NULL 
- `IsPrimaryResourceAddress` VDT_INT NOT NULL 
- `StaffAddressType` VDT_STRING64 NOT NULL 
- `StaffAddressComment` VDT_COMMENT NOT NULL 
- `StaffPrimaryPhoneNumber` VDT_PHONENUMBER NOT NULL 
- `StaffSecondaryPhoneNumber` VDT_PHONENUMBER NOT NULL 
- `StaffPagerNumber` VDT_PHONENUMBER NOT NULL 
- `StaffFaxNumber` VDT_PHONENUMBER NOT NULL 
- `StaffEMailAddress` VDT_STRING64 NOT NULL 
- `StaffOriginationDate` VDT_DATETIME NOT NULL 
- `StaffTerminationDate` VDT_DATETIME NOT NULL 
- `StaffProfession` VDT_NAME NOT NULL 
- `StaffComment` VDT_COMMENT NOT NULL 
- `StaffAdvancedPractitionerFlag` varchar NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 

---

### DWH.DimStakeHolderKeys
**Columns:** 10 | **Foreign Keys:** 0

**Columns:**
- `StkhKeyID` VDT_SERIALNUMBER NOT NULL [PK]
- `keyValue` nchar NOT NULL 
- `InstLabel` nchar NOT NULL 
- `CurrentValueIndicator` nchar NOT NULL 
- `ValidEntryIndicator` nchar NOT NULL 
- `ActiveIndicator` nchar NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 
- `ctrstkh_key_id` VDT_INT NOT NULL 
- `ctrstkh_key_cd` VDT_INT NOT NULL 

---

### DWH.DimStatusIcon
**Columns:** 10 | **Foreign Keys:** 0

**Columns:**
- `DimStatusIconID` VDT_SERIALNUMBER NOT NULL [PK]
- `ImageFile` varbinary NOT NULL 
- `MimeType` VDT_STRING20 NOT NULL 
- `StatusIconDescription` VDT_STRING256 NOT NULL 
- `SequenceNo` VDT_INT NOT NULL 
- `StatusIconActiveEntryIndicator` VDT_STRING1 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctrstatus_icon_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimStructure
**Columns:** 40 | **Foreign Keys:** 0

**Columns:**
- `DimStructureID` VDT_SERIALNUMBER NOT NULL [PK]
- `StructureSer` VDT_SERIALNUMBER NOT NULL 
- `StructureSetSer` VDT_SERIALNUMBER NOT NULL 
- `StructureId` VDT_ID_LONG NOT NULL 
- `StructureName` VDT_NAME NOT NULL 
- `StructureTypeSer` VDT_SERIALNUMBER NOT NULL 
- `DicomType` VDT_ID NOT NULL 
- `SubType` VDT_ID NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `ROINumber` VDT_INT NOT NULL 
- `ROIObservationNumber` VDT_INT NOT NULL 
- `GenerationAlgorithm` VDT_STRING16 NOT NULL 
- `GenAlgoComment` VDT_STRING64 NOT NULL 
- `DVHLineColor` VDT_INT NOT NULL 
- `DVHLineStyle` VDT_INT NOT NULL 
- `DVHLineWidth` VDT_FLOAT NOT NULL 
- `FirstSlice` VDT_INT NOT NULL 
- `LastSlice` VDT_INT NOT NULL 
- `MaterialCTValue` VDT_FLOAT NOT NULL 
- `MaterialSer` VDT_SERIALNUMBER NOT NULL 
- `ROIPhysicalProperty` VDT_STRING254 NOT NULL 
- `ROIPhysicalPropertyValue` VDT_STRING254 NOT NULL 
- `SearchCTHigh` VDT_FLOAT NOT NULL 
- `SearchCTLow` VDT_FLOAT NOT NULL 
- `EUDAlpha` VDT_FLOAT NOT NULL 
- `TCPAlpha` VDT_FLOAT NOT NULL 
- `TCPBeta` VDT_FLOAT NOT NULL 
- `TCPGamma` VDT_FLOAT NOT NULL 
- `ThicknessCm` VDT_FLOAT NOT NULL 
- `FileName` VDT_FILENAME NOT NULL 
- `ROIObservationId` VDT_ID NOT NULL 
- `ROIMaterialId` VDT_ID NOT NULL 
- `VolumeCodeDesignator` VDT_ID NOT NULL 
- `VolumeCodeVersion` VDT_ID NOT NULL 
- `VolumeCodeValue` VDT_STRING16 NOT NULL 
- `VolumeCodeMeaning` VDT_STRING64 NOT NULL 
- `Status` VDT_STRING64 NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `IsVisible` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimTemplateCycle
**Columns:** 27 | **Foreign Keys:** 1

**Columns:**
- `DimTemplateCycleID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `TemplateID` VDT_GENTMPLTID NOT NULL 
- `TemplateCreationDate` VDT_DATETIMESTAMP NOT NULL 
- `TemplateObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `TemplateDefaultFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `DiagnosisStage` VDT_STRING64 NOT NULL 
- `DiagnosisCode` VDT_DIAGNOSISCODE NOT NULL 
- `DiagnosisTableName` VDT_DIAGNOSISTABLENAME NOT NULL 
- `TemplateComment` VDT_COMMENT NOT NULL 
- `TemplateCycleObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `TreatmentCycle` VDT_STRING32 NOT NULL 
- `ctrTemplateSer` VDT_SERIALNUMBER NOT NULL 
- `TemplateRevCount` VDT_REVISIONCOUNT NOT NULL 
- `DiagnosisStageSer` VDT_SERIALNUMBER NOT NULL 
- `PayorSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `DerivedFromSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCourseSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCycleSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTemplateCycleSer` VDT_SERIALNUMBER NOT NULL 
- `TemplateCycleRevCount` VDT_REVISIONCOUNT NOT NULL 
- `TemplateCycleComment` VDT_COMMENT NOT NULL 
- `TemplateCycleHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `TemplateHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.DimToxicityGradingCriteria
**Columns:** 50 | **Foreign Keys:** 0

**Columns:**
- `DimToxicityGradingCriteriaID` VDT_SERIALNUMBER NOT NULL [PK]
- `gs_author` VDT_INT NOT NULL 
- `eff_date` VDT_DATETIME NOT NULL 
- `tr_typ` VDT_STRING30 NOT NULL 
- `ToxicityTypeENU` VDT_STRING100 NOT NULL 
- `ToxicityTypeFRA` VDT_STRING100 NOT NULL 
- `ToxicityTypeESN` VDT_STRING100 NOT NULL 
- `ToxicityTypeCHS` VDT_STRING100 NOT NULL 
- `ToxicityTypeDEU` VDT_STRING100 NOT NULL 
- `ToxicityTypeITA` VDT_STRING100 NOT NULL 
- `ToxicityTypeJPN` VDT_STRING100 NOT NULL 
- `ToxicityTypePTB` VDT_STRING100 NOT NULL 
- `ToxicityTypeSVE` VDT_STRING100 NOT NULL 
- `tr_comp_name` VDT_STRING30 NOT NULL 
- `ToxicityComponentNameENU` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameFRA` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameESN` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameCHS` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameDEU` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameITA` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameJPN` VDT_STRING100 NOT NULL 
- `ToxicityComponentNamePTB` VDT_STRING100 NOT NULL 
- `ToxicityComponentNameSVE` VDT_STRING100 NOT NULL 
- `tr_grade` VDT_INT NOT NULL 
- `tr_min_range` VDT_NUMERIC_11_4 NOT NULL 
- `tr_max_range` VDT_NUMERIC_11_4 NOT NULL 
- `upper_margin` VDT_NUMERIC_11_4 NOT NULL 
- `lower_margin` VDT_NUMERIC_11_4 NOT NULL 
- `trend` VDT_NUMERIC_11_4 NOT NULL 
- `appr_flag` VDT_STRING1 NOT NULL 
- `trans_log_tstamp` VDT_DATETIME NOT NULL 
- `trans_log_inst_id` VDT_STRING30 NOT NULL 
- `trans_log_mtstamp` VDT_DATETIME NOT NULL 
- `trans_log_minst_id` VDT_STRING30 NOT NULL 
- `trans_trf_tstamp` VDT_DATETIME NOT NULL 
- `bill_cd` VDT_STRING30 NOT NULL 
- `bill_cd_typ_id` VDT_INT NOT NULL 
- `cls_scheme_id` VDT_INT NOT NULL 
- `grading_criteria_id` VDT_INT NOT NULL 
- `tr_grading_enter_desc` VDT_STRING256 NOT NULL 
- `GradingDescENU` VDT_STRING512 NOT NULL 
- `GradingDescFRA` VDT_STRING512 NOT NULL 
- `GradingDescESN` VDT_STRING512 NOT NULL 
- `GradingDescCHS` VDT_STRING512 NOT NULL 
- `GradingDescDEU` VDT_STRING512 NOT NULL 
- `GradingDescITA` VDT_STRING512 NOT NULL 
- `GradingDescJPN` VDT_STRING512 NOT NULL 
- `GradingDescPTB` VDT_STRING512 NOT NULL 
- `GradingDescSVE` VDT_STRING512 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimTreatmentDateRangeController
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `DimTreatmentDateRangeControllerID` VDT_SERIALNUMBER NOT NULL [PK]
- `TreatmentDateTime` VDT_DATETIME NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.DimTreatmentTransaction
**Columns:** 89 | **Foreign Keys:** 3

**Columns:**
- `DimTreatmentTransactionID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `CouchLat` VDT_COUCHPARAM NOT NULL 
- `CouchLatIso` VDT_COUCHPARAM NOT NULL 
- `CouchLatOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchLng` VDT_COUCHPARAM NOT NULL 
- `CouchLngIso` VDT_COUCHPARAM NOT NULL 
- `CouchLngOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchVrt` VDT_COUCHPARAM NOT NULL 
- `CouchVrtIso` VDT_COUCHPARAM NOT NULL 
- `CouchVrtOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `HistoryNote` VDT_STRING1024 NOT NULL 
- `EnergyModeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `MetersetOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PatSupPitchOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PatSupRollOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PatSupportPitchAngle` VDT_ANGLE NOT NULL 
- `PatSupportRollAngle` VDT_ANGLE NOT NULL 
- `PatientSupportAngle` VDT_ANGLE NOT NULL 
- `PatientSupportAngleOverFlag` VDT_OVERRIDEFLAG NOT NULL 
- `SSD` VDT_FLOAT NOT NULL 
- `SSDOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `ActualCollMode` VDT_COLLMODE NOT NULL 
- `ActualGantryRtnExt` VDT_STRING16 NOT NULL 
- `ActualWedgeDose` VDT_DOSE NOT NULL 
- `BeamCurrentModulationId` VDT_ID NOT NULL 
- `BeamModifiersSet` VDT_NAME NOT NULL 
- `BeamOffCode` VDT_STRING64 NOT NULL 
- `CollModeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollRtn` VDT_ANGLE NOT NULL 
- `CollRtnOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollX1` VDT_COLLPARAM NOT NULL 
- `CollX1OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollX2` VDT_COLLPARAM NOT NULL 
- `CollX2OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollY1` VDT_COLLPARAM NOT NULL 
- `CollY1OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollY2` VDT_COLLPARAM NOT NULL 
- `CollY2OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchCorrectionLat` VDT_COUCHPARAM NOT NULL 
- `CouchCorrectionLng` VDT_COUCHPARAM NOT NULL 
- `CouchCorrectionVrt` VDT_COUCHPARAM NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `LastCorrelatedEventNumber` VDT_INT NOT NULL 
- `LastEventNumber` VDT_INT NOT NULL 
- `LastFractionNumber` VDT_INT NOT NULL 
- `LastFractionNumberCalc` VDT_INT NOT NULL 
- `MachOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `MUpDeg` VDT_MUDEG NOT NULL 
- `MUpDegOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `NumOfPaintOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `OffPlaneAngle` VDT_ANGLE NOT NULL 
- `OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `RadiationHstryType` VDT_TYPE NOT NULL 
- `SnoutPosition` VDT_DISTANCE NOT NULL 
- `SnoutPosOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `SOBPWidth` VDT_FLOAT NOT NULL 
- `StopAngle` VDT_ANGLE NOT NULL 
- `StructureSetUID` VDT_UID NOT NULL 
- `TableTopEccAngleOverFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TableTopEccentricAngle` VDT_ANGLE NOT NULL 
- `TreatmentRecordUID` VDT_UID NOT NULL 
- `TreatmentTimeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `WedgeAngle` VDT_ANGLE NOT NULL 
- `WedgeAngle2` VDT_ANGLE NOT NULL 
- `WedgeDirection` VDT_FLOAT NOT NULL 
- `WedgeDirection2` VDT_FLOAT NOT NULL 
- `WedgeDoseOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `WedgeNumber1` VDT_NUMBER NOT NULL 
- `WedgeNumber2` VDT_NUMBER NOT NULL 
- `FieldSetupNote` VDT_STRING1024 NOT NULL 
- `PSACorrection` VDT_ANGLE NOT NULL 
- `SeriesSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanAge` VDT_INT NOT NULL 
- `FileName` VDT_FILENAME NOT NULL 
- `FixLightAzimuthAngle` VDT_ANGLE NOT NULL 
- `FixLightPolarPos` VDT_ANGLE NOT NULL 
- `DoseRateOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `GantryRtn` VDT_ANGLE NOT NULL 
- `GantryRtnDirection` VDT_STRING16 NOT NULL 
- `MachineNote` VDT_STRING1024 NOT NULL 
- `GantryRtnOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `ctrRadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `ctrTreatmentRecordSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTreatmentRecordSOPClassSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimFieldID` → `DWH.DimField.DimFieldID`
- `DimPlanID` → `DWH.DimPlan.DimPlanID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`

---

### DWH.DimUser
**Columns:** 13 | **Foreign Keys:** 2

**Columns:**
- `DimUserID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimResourceID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_StakeHolder` VDT_SERIALNUMBER NOT NULL 
- `UserCUID` VDT_UID NOT NULL 
- `LanguageId` VDT_ID NOT NULL 
- `ctrAppUserSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `FirstName` VDT_STRING20 NOT NULL 
- `LastName` VDT_STRING30 NOT NULL 
- `DisplayName` VDT_STRING80 NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `ProfType` VDT_INT NOT NULL 
- `ProfDescription` VDT_STRING40 NOT NULL 

**Foreign Keys:**
- `DimResourceID` → `DWH.DimResource.DimResourceID`
- `DimResourceID_StakeHolder` → `DWH.DimResource.DimResourceID`

---

### DWH.DimUserDepartment
**Columns:** 7 | **Foreign Keys:** 2

**Columns:**
- `DimUserDepartmentID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAppUserSer` VDT_SERIALNUMBER NOT NULL 
- `AssignedToDepartment` VDT_FLAG NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimUserID` → `DWH.DimUser.DimUserID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`

---

### DWH.DimVisitEventDetail
**Columns:** 22 | **Foreign Keys:** 4

**Columns:**
- `DimVisitEventDetailID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimInstituteLocationID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_Provider` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_StartDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_EndDateTime` VDT_SERIALNUMBER NOT NULL 
- `EventType` VDT_STRING60 NOT NULL 
- `EventTypeDescription` VDT_STRING100 NOT NULL 
- `PatientIndicator` VDT_STRING2 NOT NULL 
- `ProfIndicator` VDT_STRING2 NOT NULL 
- `LocationIndicator` VDT_STRING2 NOT NULL 
- `PatientUnavailComment` VDT_STRING256 NOT NULL 
- `EventStartDateTime` VDT_DATETIME NOT NULL 
- `EventEndDateTime` VDT_DATETIME NOT NULL 
- `ValidEntryIndicator` VDT_STRING2 NOT NULL 
- `ctrunavl_hdr_id` VDT_INT NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `EventName` VDT_STRING40 NOT NULL 
- `SchEventName` VDT_STRING40 NOT NULL 

**Foreign Keys:**
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimInstituteLocationID` → `DWH.DimInstituteLocation.DimInstituteLocationID`

---

### DWH.DoseContributionModel
**Columns:** 19 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_ID NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `PrimaryRefPoint` VDT_FLAG NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `PlannedFieldDose` VDT_FLOAT NOT NULL 
- `DeliveredFieldDose` VDT_FLOAT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `CorrectionNote` VDT_COMMENT NOT NULL 
- `CorrectionDateTime` VDT_DATETIME NOT NULL 
- `RefPointLogSer` bigint NOT NULL 
- `DoseCorrectionLogSer` bigint NOT NULL 

---

### DWH.ETLQueriesMetadata
**Columns:** 13 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_BIGNUMBER NOT NULL 
- `PackageName` VDT_STRING50 NOT NULL [PK]
- `MigrationType` VDT_STRING1 NOT NULL [PK]
- `PackageStageOrder` VDT_NUMBER NOT NULL [PK]
- `QueryExecOrder` VDT_NUMBER NOT NULL [PK]
- `QueryType` VDT_STRING1 NOT NULL 
- `SourceQuery` varchar NOT NULL 
- `LastCTVersion` VDT_BIGNUMBER NOT NULL 
- `CurrentCTVersion` VDT_BIGNUMBER NOT NULL 
- `DateCreated` VDT_DATETIME NOT NULL 
- `DateModified` VDT_DATETIME NOT NULL 
- `UserCreated` VDT_STRING50 NOT NULL 
- `UserModified` VDT_STRING50 NOT NULL 

---

### DWH.FactActivityBilling
**Columns:** 105 | **Foreign Keys:** 31

**Columns:**
- `FactActivityBillingID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimProcedureCodeID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ActivityCategory` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_Activity` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimDoctorID` VDT_SERIALNUMBER NOT NULL 
- `DimDoctorID_AttendingOncologist` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_MarkedCompletedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ExportedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ChargeWaivedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ReviewedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_CreditedBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_FromDateOfService` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ToDateOfService` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ExportedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_MarkedCompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreditExportedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreditedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TemplateCreationDate` VDT_SERIALNUMBER NOT NULL 
- `DimPayorID` VDT_SERIALNUMBER NOT NULL 
- `PrimaryGlobalCharge` VDT_MONEY NOT NULL 
- `PrimaryTechnicalCharge` VDT_MONEY NOT NULL 
- `PrimaryProfessionalCharge` VDT_MONEY NOT NULL 
- `OtherProfessionalCharge` VDT_MONEY NOT NULL 
- `OtherTechnicalCharge` VDT_MONEY NOT NULL 
- `OtherGlobalCharge` VDT_MONEY NOT NULL 
- `ChargeForecast` VDT_MONEY NOT NULL 
- `ActualCharge` VDT_MONEY NOT NULL 
- `ProfessionalRVU` VDT_FLOAT NOT NULL 
- `GlobalRVU` VDT_FLOAT NOT NULL 
- `TechnicalRVU` VDT_FLOAT NOT NULL 
- `ActivityCost` VDT_MONEY NOT NULL 
- `WorkUnit` VDT_FLOAT NOT NULL 
- `AccountBillingCode` VDT_STRING128 NOT NULL 
- `AccountBillingCodeStartDate` VDT_DATETIME NOT NULL 
- `AccountBillingCodeEndDate` VDT_DATETIME NOT NULL 
- `AccountBillingCodeObjectStatus` VDT_STRING16 NOT NULL 
- `AccountBillingCodeInPatientFlag` VDT_INT NOT NULL 
- `AccountBillingCodeValidEntryInd` VDT_STRING1 NOT NULL 
- `FromDateOfService` VDT_DATETIME NOT NULL 
- `ToDateOfService` VDT_DATETIME NOT NULL 
- `CompletedDateTime` VDT_DATETIME NOT NULL 
- `ExportedDateTime` VDT_DATETIME NOT NULL 
- `MarkedCompletedDateTime` VDT_DATETIME NOT NULL 
- `CreditExportedDateTime` VDT_DATETIME NOT NULL 
- `CreditedDateTime` VDT_DATETIME NOT NULL 
- `ReviewedDateTime` VDT_DATETIME NOT NULL 
- `CreditNote` VDT_STRING254 NOT NULL 
- `AllModifierCodes` VDT_STRING512 NOT NULL 
- `CreditAmount` VDT_MONEY NOT NULL 
- `IsScheduled` VDT_STRING1 NOT NULL 
- `DiagnosisId` VDT_STRING1024 NOT NULL 
- `DiagnosisDescription` VDT_STRING1024 NOT NULL 
- `ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ActivityInstance_ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ActInstProcCode_ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ActInstProcCode_Comment` VDT_COMMENT NOT NULL 
- `ActivityCaptureRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActivityInstanceRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActivityCodeMdRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ProcedureCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `AccountBillingCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActInstProcCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `CreditRevCount` VDT_REVISIONCOUNT NOT NULL 
- `TemplateID` VDT_GENTMPLTID NOT NULL 
- `TemplateRevCount` VDT_REVISIONCOUNT NOT NULL 
- `TemplateCreationDate` VDT_DATETIME NOT NULL 
- `PatientStatus` VDT_STATUS32 NOT NULL 
- `InPatientFlag` VDT_STRING10 NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTemplateSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTemplateCycleSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCaptureSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActInstProcCodeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAccountBillingCodeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCreditSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDiagnosisSer` VDT_STRING1024 NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer_Activity` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimUserID_CompletedByUser` VDT_SERIALNUMBER NOT NULL 
- `BillEventDescription` VDT_STRING254 NOT NULL 
- `DimLookupID_BillEventType` VDT_SERIALNUMBER NOT NULL 
- `BillEventUnits` VDT_INT NOT NULL 
- `BillEventStatus` VDT_STRING1 NOT NULL 
- `BillingInventoryID` VDT_STRING10 NOT NULL 
- `BillItemDescription` VDT_STRING256 NOT NULL 
- `DimDrugID` VDT_SERIALNUMBER NOT NULL 
- `BillingAccountID` VDT_INT NOT NULL 
- `DimInstituteLocationID` VDT_SERIALNUMBER NOT NULL 
- `OverrideIndicator` VDT_STRING1 NOT NULL 
- `DimDoctorID_Referring` VDT_SERIALNUMBER NOT NULL 
- `DoseWastageAmount` VDT_FLOAT NOT NULL 
- `DimLookupID_DoseWastageUnit` VDT_SERIALNUMBER NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `ctrbill_event_id` VDT_INT NOT NULL 
- `MOROIndicator` VDT_STRING2 NOT NULL 
- `DimUserID_Physician` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendingOncologistSer` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 

**Foreign Keys:**
- `DimProcedureCodeID` → `DWH.DimProcedureCode.DimProcedureCodeID`
- `DimActivityID` → `DWH.DimActivity.DimActivityID`
- `DimLookupID_ActivityCategory` → `DWH.DimLookup.DimLookupID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimDoctorID` → `DWH.DimDoctor.DimDoctorID`
- `DimDoctorID_AttendingOncologist` → `DWH.DimDoctor.DimDoctorID`
- `DimUserID_MarkedCompletedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_ExportedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_ChargeWaivedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_ReviewedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_CreditedBy` → `DWH.DimUser.DimUserID`
- `DimDateID_FromDateOfService` → `DWH.DimDate.DimDateID`
- `DimDateID_ToDateOfService` → `DWH.DimDate.DimDateID`
- `DimDateID_CompletedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ExportedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_MarkedCompletedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_CreditExportedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_CreditedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_TemplateCreationDate` → `DWH.DimDate.DimDateID`
- `DimPayorID` → `DWH.DimPayor.DimPayorID`
- `DimUserID_CompletedByUser` → `DWH.DimUser.DimUserID`
- `DimLookupID_BillEventType` → `DWH.DimLookup.DimLookupID`
- `DimDrugID` → `DWH.DimDrug.DimDrugID`
- `DimInstituteLocationID` → `DWH.DimInstituteLocation.DimInstituteLocationID`
- `DimDoctorID_Referring` → `DWH.DimDoctor.DimDoctorID`
- `DimLookupID_DoseWastageUnit` → `DWH.DimLookup.DimLookupID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`
- `DimUserID_Physician` → `DWH.DimUser.DimUserID`

---

### DWH.FactActivityBillingNoCapture
**Columns:** 103 | **Foreign Keys:** 30

**Columns:**
- `FactActivityBillingID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimProcedureCodeID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ActivityCategory` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_Activity` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimDoctorID` VDT_SERIALNUMBER NOT NULL 
- `DimDoctorID_AttendingOncologist` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_MarkedCompletedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ExportedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ChargeWaivedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ReviewedBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_CreditedBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_FromDateOfService` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ToDateOfService` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ExportedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_MarkedCompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreditExportedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreditedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TemplateCreationDate` VDT_SERIALNUMBER NOT NULL 
- `PrimaryGlobalCharge` VDT_MONEY NOT NULL 
- `PrimaryTechnicalCharge` VDT_MONEY NOT NULL 
- `PrimaryProfessionalCharge` VDT_MONEY NOT NULL 
- `OtherProfessionalCharge` VDT_MONEY NOT NULL 
- `OtherTechnicalCharge` VDT_MONEY NOT NULL 
- `OtherGlobalCharge` VDT_MONEY NOT NULL 
- `ChargeForecast` VDT_MONEY NOT NULL 
- `ActualCharge` VDT_MONEY NOT NULL 
- `ProfessionalRVU` VDT_FLOAT NOT NULL 
- `GlobalRVU` VDT_FLOAT NOT NULL 
- `TechnicalRVU` VDT_FLOAT NOT NULL 
- `ActivityCost` VDT_MONEY NOT NULL 
- `WorkUnit` VDT_FLOAT NOT NULL 
- `AccountBillingCode` VDT_STRING128 NOT NULL 
- `AccountBillingCodeStartDate` VDT_DATETIME NOT NULL 
- `AccountBillingCodeEndDate` VDT_DATETIME NOT NULL 
- `AccountBillingCodeObjectStatus` VDT_STRING16 NOT NULL 
- `AccountBillingCodeInPatientFlag` VDT_INT NOT NULL 
- `AccountBillingCodeValidEntryInd` VDT_STRING1 NOT NULL 
- `FromDateOfService` VDT_DATETIME NOT NULL 
- `ToDateOfService` VDT_DATETIME NOT NULL 
- `CompletedDateTime` VDT_DATETIME NOT NULL 
- `ExportedDateTime` VDT_DATETIME NOT NULL 
- `MarkedCompletedDateTime` VDT_DATETIME NOT NULL 
- `CreditExportedDateTime` VDT_DATETIME NOT NULL 
- `CreditedDateTime` VDT_DATETIME NOT NULL 
- `ReviewedDateTime` VDT_DATETIME NOT NULL 
- `CreditNote` VDT_STRING254 NOT NULL 
- `AllModifierCodes` VDT_STRING512 NOT NULL 
- `CreditAmount` VDT_MONEY NOT NULL 
- `IsScheduled` VDT_STRING1 NOT NULL 
- `DiagnosisId` VDT_STRING1024 NOT NULL 
- `DiagnosisDescription` VDT_STRING1024 NOT NULL 
- `ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ActivityInstance_ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ActInstProcCode_ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `ActInstProcCode_Comment` VDT_COMMENT NOT NULL 
- `ActivityCaptureRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActivityInstanceRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActivityCodeMdRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ProcedureCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `AccountBillingCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActInstProcCodeRevCount` VDT_REVISIONCOUNT NOT NULL 
- `CreditRevCount` VDT_REVISIONCOUNT NOT NULL 
- `TemplateID` VDT_GENTMPLTID NOT NULL 
- `TemplateRevCount` VDT_REVISIONCOUNT NOT NULL 
- `TemplateCreationDate` VDT_DATETIME NOT NULL 
- `PatientStatus` VDT_STATUS32 NOT NULL 
- `InPatientFlag` VDT_STRING10 NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTemplateSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTemplateCycleSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCaptureSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActInstProcCodeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAccountBillingCodeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCreditSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDiagnosisSer` VDT_STRING1024 NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer_Activity` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimUserID_CompletedByUser` VDT_SERIALNUMBER NOT NULL 
- `BillEventDescription` VDT_STRING254 NOT NULL 
- `DimLookupID_BillEventType` VDT_SERIALNUMBER NOT NULL 
- `BillEventUnits` VDT_INT NOT NULL 
- `BillEventStatus` VDT_STRING1 NOT NULL 
- `BillingInventoryID` VDT_STRING10 NOT NULL 
- `BillItemDescription` VDT_STRING256 NOT NULL 
- `DimDrugID` VDT_SERIALNUMBER NOT NULL 
- `BillingAccountID` VDT_INT NOT NULL 
- `DimInstituteLocationID` VDT_SERIALNUMBER NOT NULL 
- `OverrideIndicator` VDT_STRING1 NOT NULL 
- `DimDoctorID_Referring` VDT_SERIALNUMBER NOT NULL 
- `DoseWastageAmount` VDT_FLOAT NOT NULL 
- `DimLookupID_DoseWastageUnit` VDT_SERIALNUMBER NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `ctrbill_event_id` VDT_INT NOT NULL 
- `MOROIndicator` VDT_STRING2 NOT NULL 
- `DimUserID_Physician` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendingOncologistSer` VDT_SERIALNUMBER NOT NULL 

**Foreign Keys:**
- `DimProcedureCodeID` → `DWH.DimProcedureCode.DimProcedureCodeID`
- `DimActivityID` → `DWH.DimActivity.DimActivityID`
- `DimLookupID_ActivityCategory` → `DWH.DimLookup.DimLookupID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimDoctorID` → `DWH.DimDoctor.DimDoctorID`
- `DimDoctorID_AttendingOncologist` → `DWH.DimDoctor.DimDoctorID`
- `DimUserID_MarkedCompletedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_ExportedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_ChargeWaivedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_ReviewedBy` → `DWH.DimUser.DimUserID`
- `DimUserID_CreditedBy` → `DWH.DimUser.DimUserID`
- `DimDateID_FromDateOfService` → `DWH.DimDate.DimDateID`
- `DimDateID_ToDateOfService` → `DWH.DimDate.DimDateID`
- `DimDateID_CompletedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ExportedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_MarkedCompletedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_CreditExportedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_CreditedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_TemplateCreationDate` → `DWH.DimDate.DimDateID`
- `DimUserID_CompletedByUser` → `DWH.DimUser.DimUserID`
- `DimLookupID_BillEventType` → `DWH.DimLookup.DimLookupID`
- `DimDrugID` → `DWH.DimDrug.DimDrugID`
- `DimInstituteLocationID` → `DWH.DimInstituteLocation.DimInstituteLocationID`
- `DimDoctorID_Referring` → `DWH.DimDoctor.DimDoctorID`
- `DimLookupID_DoseWastageUnit` → `DWH.DimLookup.DimLookupID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`
- `DimUserID_Physician` → `DWH.DimUser.DimUserID`

---

### DWH.FactActivityCaptureAttribute
**Columns:** 9 | **Foreign Keys:** 1

**Columns:**
- `FactActivityCaptureAttributeID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimActivityAttributeID` VDT_SERIALNUMBER NOT NULL 
- `AttributeValue` VDT_STRING254 NOT NULL 
- `ctrActivityCaptureSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityCaptureRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ctrActivityCaptureAttributeSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityCaptureAttrRevCount` VDT_REVISIONCOUNT NOT NULL 
- `ActivityCaptureAttributeObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimActivityAttributeID` → `DWH.DimActivityAttribute.DimActivityAttributeID`

---

### DWH.FactActivityDiagnosis
**Columns:** 9 | **Foreign Keys:** 6

**Columns:**
- `FactActivityDiagnosisID` VDT_SERIALNUMBER NOT NULL [PK]
- `FactActivityBillingID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `FactPatientDiagnosisID` VDT_SERIALNUMBER NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID_BodySystem` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID` VDT_SERIALNUMBER NOT NULL 
- `IsPrimary` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `FactActivityBillingID` → `DWH.FactActivityBilling.FactActivityBillingID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `FactPatientDiagnosisID` → `DWH.FactPatientDiagnosis.FactPatientDiagnosisID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`
- `DimDxSiteID_BodySystem` → `DWH.DimDxSite.DimDxSiteID`
- `DimDxSiteID` → `DWH.DimDxSite.DimDxSiteID`

---

### DWH.FactBrachySourcePosition
**Columns:** 16 | **Foreign Keys:** 3

**Columns:**
- `FactBrachySourcePositionID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimBrachyFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimRadioactiveModelSourceID` VDT_SERIALNUMBER NOT NULL 
- `DimStructureID` VDT_SERIALNUMBER NOT NULL 
- `SourcePositionId` VDT_ID NOT NULL 
- `SourcePositionName` VDT_NAME NOT NULL 
- `DwellPosition` VDT_FLOAT NOT NULL 
- `DwellTime` VDT_FLOAT NOT NULL 
- `DwellTimeLockedFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `DwellTimeMaxLimit` VDT_FLOAT NOT NULL 
- `DwellTimeMinLimit` VDT_FLOAT NOT NULL 
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `ctrStructureSer` VDT_SERIALNUMBER NOT NULL 
- `ctrSourcePositionSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimBrachyFieldID` → `DWH.DimBrachyField.DimBrachyFieldID`
- `DimRadioactiveModelSourceID` → `DWH.DimRadioactiveModelSource.DimRadioactiveModelSourceID`
- `DimUserID` → `DWH.DimUser.DimUserID`

---

### DWH.FactBrachyTreatment
**Columns:** 113 | **Foreign Keys:** 21

**Columns:**
- `FactBrachyTreatmentID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `TreatmentRecord_DimActualMachineID` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedMachineID` VDT_SERIALNUMBER NOT NULL 
- `ActualMachineAuthorization` VDT_NAME NOT NULL 
- `MachOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TreatmentRecordHstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `TreatmentRecordHstryTaskName` VDT_TASKNAME NOT NULL 
- `TreatmentRecordDateTime` VDT_DATETIMESTAMP NOT NULL 
- `TreatmentRecordNoOfFractions` VDT_COUNT NOT NULL 
- `RadiationHstryType` VDT_TYPE NOT NULL 
- `TreatmentDeliveryType` VDT_STRING16 NOT NULL 
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_FieldTechnique` VDT_SERIALNUMBER NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `RadiationName` VDT_STRING64 NOT NULL 
- `RadiationNumber` VDT_INT NOT NULL 
- `DimLookupID_TechniqueLabel` VDT_SERIALNUMBER NOT NULL 
- `RadiationType` VDT_ENERGYMODE NOT NULL 
- `DimDateID_TreatmentStartDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentEndDate` VDT_SERIALNUMBER NOT NULL 
- `TreatmentStartTime` VDT_DATETIME NOT NULL 
- `TreatmentEndTime` VDT_DATETIME NOT NULL 
- `TreatmentTime` VDT_TIME NOT NULL 
- `TreatmentTimeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TerminationStatus` VDT_STATUS16 NOT NULL 
- `FractionNumber` VDT_INT NOT NULL 
- `DimDateID_RadiationHstryApprovalDate` VDT_SERIALNUMBER NOT NULL 
- `RadiationHstryApprovalDate` VDT_DATETIME NOT NULL 
- `RadiationHstryUserName1` VDT_NAME NOT NULL 
- `RadiationHstryUserName2` VDT_STRING32 NOT NULL 
- `RadiationHstryUserName3` VDT_STRING32 NOT NULL 
- `OverrideFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `RadiationHstryDateTime` VDT_DATETIME NOT NULL 
- `RadiationHstryTaskName` VDT_TASKNAME NOT NULL 
- `RadiationHstryHistoryNote` VDT_STRING NOT NULL 
- `RadiationHstryMachineNote` VDT_STRING NOT NULL 
- `RadiationHstryFieldSetupNote` VDT_STRING NOT NULL 
- `ActualDose` VDT_DOSE NOT NULL 
- `BrachyTreatmentType` VDT_STRING16 NOT NULL 
- `ChannelNumber` VDT_INT NOT NULL 
- `ChannelLength` VDT_FLOAT NOT NULL 
- `SpecifiedChannelTotalTime` VDT_FLOAT NOT NULL 
- `ChannelReferenceAirKerma` VDT_FLOAT NOT NULL 
- `DeliveredChannelTotalTime` VDT_FLOAT NOT NULL 
- `SpecifiedNumberOfPulses` VDT_INT NOT NULL 
- `DeliveredNumberOfPulses` VDT_INT NOT NULL 
- `SpecifiedPulseRepetitionInterval` VDT_FLOAT NOT NULL 
- `DeliveredPulseRepetitionInterval` VDT_FLOAT NOT NULL 
- `SourceSerialNumber` VDT_MANUFACTSERIALNO NOT NULL 
- `SourceIsotopeName` VDT_NAME NOT NULL 
- `ReferenceAirKermaRate` VDT_FLOAT NOT NULL 
- `SourceStrengthReferenceDateTime` VDT_DATETIME NOT NULL 
- `NumberOfSourcePositions` VDT_INT NOT NULL 
- `DimUserID_CompletedByUser` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ClinicalStatus` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CourseStartDateTime` VDT_SERIALNUMBER NOT NULL 
- `CourseStartDateTime` VDT_DATETIME NOT NULL 
- `DimDateID_CourseCompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `CourseCompletedDateTime` VDT_DATETIME NOT NULL 
- `PlanTreatmentType` VDT_TREATMENTTYPE NOT NULL 
- `PrescribedPercentage` VDT_FLOAT NOT NULL 
- `PrescribedDose` VDT_DOSE NOT NULL 
- `FirstTreatmentDate` VDT_DATETIME NOT NULL 
- `LastTreatmentDate` VDT_DATETIME NOT NULL 
- `PlanApprovedStatusDate` VDT_DATETIME NOT NULL 
- `AuthorizationDate` VDT_DATETIME NOT NULL 
- `DimLookupID_TreatmentIntentType` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_FirstTreatmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_LastTreatmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PlanApprovedStatusDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AuthorizationDate` VDT_SERIALNUMBER NOT NULL 
- `IsActive` VDT_INT NOT NULL 
- `PlannedFieldDose` VDT_FLOAT NOT NULL 
- `DeliveredFieldDose` VDT_FLOAT NOT NULL 
- `DimDateID_CorrectionDateTime` VDT_SERIALNUMBER NOT NULL 
- `CorrectionDateTime` VDT_DATETIME NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `RefPointName` VDT_NAME NOT NULL 
- `DoseCorrectionComment` VDT_COMMENT NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `PrimaryFlag` VDT_INT NOT NULL 
- `FractionsDelivered` VDT_INT NOT NULL 
- `FractionsPlanned` VDT_INT NOT NULL 
- `FractionsRemaining` VDT_INT NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `DoseRemainingInFraction` VDT_FLOAT NOT NULL 
- `DoseDelta` VDT_DOSE NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCourseSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRadiationSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPhysicianIntentSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointLogSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDoseCorrectionLogSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointHstrySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActualMachineSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPlannedMachineSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTreatmentRecordSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `DimPlanID` → `DWH.DimPlan.DimPlanID`
- `TreatmentRecord_DimActualMachineID` → `DWH.DimMachine.DimMachineID`
- `DimPlannedMachineID` → `DWH.DimMachine.DimMachineID`
- `DimFieldID` → `DWH.DimField.DimFieldID`
- `DimLookupID_FieldTechnique` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_TechniqueLabel` → `DWH.DimLookup.DimLookupID`
- `DimDateID_TreatmentStartDate` → `DWH.DimDate.DimDateID`
- `DimDateID_TreatmentEndDate` → `DWH.DimDate.DimDateID`
- `DimDateID_RadiationHstryApprovalDate` → `DWH.DimDate.DimDateID`
- `DimUserID_CompletedByUser` → `DWH.DimUser.DimUserID`
- `DimLookupID_ClinicalStatus` → `DWH.DimLookup.DimLookupID`
- `DimDateID_CourseStartDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_CourseCompletedDateTime` → `DWH.DimDate.DimDateID`
- `DimLookupID_TreatmentIntentType` → `DWH.DimLookup.DimLookupID`
- `DimDateID_FirstTreatmentDate` → `DWH.DimDate.DimDateID`
- `DimDateID_LastTreatmentDate` → `DWH.DimDate.DimDateID`
- `DimDateID_PlanApprovedStatusDate` → `DWH.DimDate.DimDateID`
- `DimDateID_AuthorizationDate` → `DWH.DimDate.DimDateID`
- `DimDateID_CorrectionDateTime` → `DWH.DimDate.DimDateID`

---

### DWH.FactCourseDiagnosis
**Columns:** 9 | **Foreign Keys:** 5

**Columns:**
- `FactCourseDiagnosisID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `FactPatientDiagnosisID` VDT_SERIALNUMBER NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID_BodySystem` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID` VDT_SERIALNUMBER NOT NULL 
- `IsPrimary` VDT_INT NOT NULL 
- `DimLookupID_DiagnosisObjectStatus` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `FactPatientDiagnosisID` → `DWH.FactPatientDiagnosis.FactPatientDiagnosisID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`
- `DimDxSiteID_BodySystem` → `DWH.DimDxSite.DimDxSiteID`
- `DimDxSiteID` → `DWH.DimDxSite.DimDxSiteID`

---

### DWH.FactDVH
**Columns:** 24 | **Foreign Keys:** 4

**Columns:**
- `FactDVHID` VDT_SERIALNUMBER NOT NULL [PK]
- `DoseValue` float NOT NULL 
- `Volume` float NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimStructureID` VDT_SERIALNUMBER NOT NULL 
- `ctrPlanSer` VDT_SERIALNUMBER NOT NULL 
- `ctrCourseSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrStructureSer` VDT_SERIALNUMBER NOT NULL 
- `ctrStructureSetSer` VDT_SERIALNUMBER NOT NULL 
- `MaxDoseUnit` varchar NOT NULL 
- `MinDoseUnit` varchar NOT NULL 
- `MaxDose` decimal NOT NULL 
- `MinDose` decimal NOT NULL 
- `Coverage` float NOT NULL 
- `SamplingCoverage` float NOT NULL 
- `StdDev` float NOT NULL 
- `DataArrayVolume` float NOT NULL 
- `RelativeDose` float NOT NULL 
- `RelativeVolume` float NOT NULL 
- `RelativeVolumeRounded` float NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `DimPlanID` → `DWH.DimPlan.DimPlanID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimStructureID` → `DWH.DimStructure.DimStructureID`

---

### DWH.FactDVHToxicity
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `FactDVHToxicityID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `FactPatientToxicityID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `IsAcute` VDT_INT NOT NULL 

---

### DWH.FactInVivoDosimetry
**Columns:** 25 | **Foreign Keys:** 4

**Columns:**
- `FactInVivoDosimetryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_InVivoDate` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_CreationUserName` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreationDate` VDT_SERIALNUMBER NOT NULL 
- `InVivoDate` VDT_DATETIMESTAMP NOT NULL 
- `InVivoVendorName` VDT_NAME NOT NULL 
- `DosimeterType` VDT_STRING64 NOT NULL 
- `DosimeterId` VDT_STRING64 NOT NULL 
- `DosimeterLocation` VDT_STRING128 NOT NULL 
- `FieldId` VDT_ID NOT NULL 
- `FieldName` VDT_NAME NOT NULL 
- `ExpectedDose` VDT_DOSE NOT NULL 
- `DeliveredDose` VDT_DOSE NOT NULL 
- `ToleranceValue` VDT_FLOAT NOT NULL 
- `CreationDate` VDT_DATETIMESTAMP NOT NULL 
- `PlanUID` VDT_UID NOT NULL 
- `FieldGroupNumber` VDT_INT NOT NULL 
- `ObjectStatus` VDT_OBJECTSTATUS NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `ctrInVivoDosimetrySer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimDateID_InVivoDate` → `DWH.DimDate.DimDateID`
- `DimUserID_CreationUserName` → `DWH.DimUser.DimUserID`
- `DimDateID_CreationDate` → `DWH.DimDate.DimDateID`

---

### DWH.FactPatient
**Columns:** 22 | **Foreign Keys:** 12

**Columns:**
- `FactPatientID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimNationalityID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Race` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Gender` VDT_SERIALNUMBER NOT NULL 
- `DimLocationID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimPrimaryOncologistID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PatientCreation` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PatientDischarge` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PatientAdmission` VDT_SERIALNUMBER NOT NULL 
- `DimPrimaryReferringPhysicianID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_PatientStatus` VDT_SERIALNUMBER NOT NULL 
- `PatientCreationDate` VDT_DATETIME NOT NULL 
- `PatientAdmissionDate` VDT_DATETIME NOT NULL 
- `PatientDischargeDate` VDT_DATETIME NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimMedoncHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimMedoncPrimaryOncologistID` VDT_SERIALNUMBER NOT NULL 
- `DimMedoncPrimaryReferringPhysicianID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_PatientDeathCause` VDT_SERIALNUMBER NOT NULL 
- `MOROIndicator` VDT_STRING10 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimNationalityID` → `DWH.DimNationality.DimNationalityID`
- `DimLookupID_Race` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Gender` → `DWH.DimLookup.DimLookupID`
- `DimLocationID` → `DWH.DimLocation.DimLocationID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimPrimaryOncologistID` → `DWH.DimDoctor.DimDoctorID`
- `DimDateID_PatientCreation` → `DWH.DimDate.DimDateID`
- `DimDateID_PatientDischarge` → `DWH.DimDate.DimDateID`
- `DimDateID_PatientAdmission` → `DWH.DimDate.DimDateID`
- `DimPrimaryReferringPhysicianID` → `DWH.DimDoctor.DimDoctorID`
- `DimLookupID_PatientStatus` → `DWH.DimLookup.DimLookupID`

---

### DWH.FactPatientAllergy
**Columns:** 20 | **Foreign Keys:** 4

**Columns:**
- `FactPatientAllergyID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AllergyType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AllergySeverity` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AllergyStartedOn` VDT_SERIALNUMBER NOT NULL 
- `AllergicResponse` VDT_STRING1024 NOT NULL 
- `AllergyDescription` VDT_STRING1024 NOT NULL 
- `AllergicDrugDescription` VDT_STRING20 NOT NULL 
- `AllergicReaction` VDT_STRING20 NOT NULL 
- `AllergyTypeDesc` VDT_STRING40 NOT NULL 
- `AllergyCode` VDT_STRING6 NOT NULL 
- `AllergySeverityCode` VDT_STRING6 NOT NULL 
- `AllergySeverityDescripton` VDT_STRING40 NOT NULL 
- `AllergyAgentName` VDT_STRING100 NOT NULL 
- `AllergyComment` VDT_STRING512 NOT NULL 
- `ctrallergy_id` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `NoKnownAllergy` VDT_STRING1 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_AllergyType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_AllergySeverity` → `DWH.DimLookup.DimLookupID`
- `DimDateID_AllergyStartedOn` → `DWH.DimDate.DimDateID`

---

### DWH.FactPatientCurrentMedication
**Columns:** 59 | **Foreign Keys:** 1

**Columns:**
- `FactPatientCurrentMedicationID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_DateStarted` VDT_SERIALNUMBER NOT NULL 
- `DoseLevel` VDT_INT NOT NULL 
- `CumulativeDoseToDate` numeric NOT NULL 
- `DimDateID_AdministrationDateEnded` VDT_SERIALNUMBER NOT NULL 
- `UnitOfMeasure` VDT_INT NOT NULL 
- `PatientConditionDescInd` nvarchar NOT NULL 
- `CumulativeDoseUnitOfMeasure` VDT_INT NOT NULL 
- `DoseAmount` numeric NOT NULL 
- `DimDateID_DateOfLastDose` VDT_SERIALNUMBER NOT NULL 
- `AdminDoseFrqencyUnit` VDT_INT NOT NULL 
- `AdminFrequencyX` VDT_INT NOT NULL 
- `AdminFrequencyUnit` VDT_INT NOT NULL 
- `AdminDuration` VDT_INT NOT NULL 
- `AdminRoute` VDT_INT NOT NULL 
- `AdminDurationUnit` VDT_INT NOT NULL 
- `statusOfAgent` VDT_STRING1 NOT NULL 
- `ExternalAgentFlag` VDT_STRING1 NOT NULL 
- `MethodOfAdmin` VDT_STRING256 NOT NULL 
- `DrugDescId` VDT_STRING6 NOT NULL 
- `DateApproxIndicator` VDT_STRING1 NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `PRNIndicator` VDT_STRING1 NOT NULL 
- `GeneralOrders` nvarchar NOT NULL 
- `DoseAmountRange` numeric NOT NULL 
- `MedispanActiveIndicator` VDT_STRING1 NOT NULL 
- `DimDateID_MedispanIndicatorChangeDate` VDT_SERIALNUMBER NOT NULL 
- `CourseDescription` VDT_STRING256 NOT NULL 
- `DayOfWeekFreqUnit` VDT_INT NOT NULL 
- `WeekFreqUnit` VDT_INT NOT NULL 
- `DateStartedCode` VDT_INT NOT NULL 
- `DimDateID_LastDispensedDate` VDT_SERIALNUMBER NOT NULL 
- `AgentClass` VDT_STRING10 NOT NULL 
- `PRNReasonType` VDT_INT NOT NULL 
- `DoseStrength` VDT_STRING15 NOT NULL 
- `StrengthUnit` VDT_INT NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `PriorCumulativeDose` numeric NOT NULL 
- `CumulativeDoseComment` nvarchar NOT NULL 
- `PriorCumulativeUnitOfMeasure` VDT_INT NOT NULL 
- `TakeAsDirectedIndicator` VDT_STRING1 NOT NULL 
- `AdminFrequencyUpperX` VDT_INT NOT NULL 
- `RevisionNumber` VDT_INT NOT NULL 
- `ApplicationCode` VDT_STRING10 NOT NULL 
- `DateEndedCode` VDT_INT NOT NULL 
- `ErrorReasonText` VDT_STRING256 NOT NULL 
- `DrugLotNumber` VDT_STRING30 NOT NULL 
- `AgentManufacturerId` VDT_INT NOT NULL 
- `DimDateID_ExpiryDate` VDT_SERIALNUMBER NOT NULL 
- `AdminSiteIndicator` VDT_INT NOT NULL 
- `UniqueCCDAIndicator` VDT_STRING80 NOT NULL 
- `DimDateID_IntfReconcileDate` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctragt_name` VDT_STRING50 NOT NULL 
- `ctrdosage_form` VDT_INT NOT NULL 
- `ctrdate_started` VDT_DATETIME NOT NULL 
- `LogID` VDT_BIGNUMBER NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.FactPatientDiagnosis
**Columns:** 83 | **Foreign Keys:** 29

**Columns:**
- `FactPatientDiagnosisID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `DimICDOSiteID` VDT_SERIALNUMBER NOT NULL 
- `DimCellTypeID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_DiagnosisStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Ranking` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Source` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_HistoricDxFlag` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_CellCategory` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_CellGrade` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Laterality` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Stage` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_StageStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ERStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_PRStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Her2neuMethodType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Her2neuStatusType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Her2neuMethod2Type` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Her2neuStatus2Type` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Recurrence` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Invasive` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ConfirmedDx` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_DiagnosisType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_DxMethodType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ICDOVersion` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_StageScheme` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID_BodySystem` VDT_SERIALNUMBER NOT NULL 
- `DimDxSiteID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_DiagnosisStatusDate` VDT_SERIALNUMBER NOT NULL 
- `DxDate` VDT_STRING50 NOT NULL 
- `OnSetDateCode` VDT_INT NOT NULL 
- `DiagnosisStatusDate` VDT_DATETIME NOT NULL 
- `DiagnosisDescription` VDT_STRING512 NOT NULL 
- `ClinicalDescription` VDT_STRING512 NOT NULL 
- `HistoricDetails` VDT_STRING254 NOT NULL 
- `Comments` VDT_COMMENT NOT NULL 
- `PathologyComments` VDT_STRING256 NOT NULL 
- `Behaviour` VDT_STRING50 NOT NULL 
- `DistantMets` VDT_STRING30 NOT NULL 
- `Nodes` VDT_INT NOT NULL 
- `NodesPositive` VDT_INT NOT NULL 
- `Size` decimal NOT NULL 
- `StageCriteria` VDT_STRING512 NOT NULL 
- `Stagebasis` VDT_STRING40 NOT NULL 
- `StageScheme` VDT_STRING64 NOT NULL 
- `SPhase` decimal NOT NULL 
- `MethodDescription` VDT_STRING254 NOT NULL 
- `CoresTaken` VDT_INT NOT NULL 
- `CoresPositive` VDT_INT NOT NULL 
- `GleasonPrimary` VDT_INT NOT NULL 
- `GleasonSecondary` VDT_INT NOT NULL 
- `GleasonTotal` VDT_INT NOT NULL 
- `GleasonScore` VDT_INT NOT NULL 
- `ObjectStatus` VDT_STRING16 NOT NULL 
- `HistologyCode` VDT_STRING16 NOT NULL 
- `HistologyTableName` VDT_STRING64 NOT NULL 
- `TStage` VDT_STRING32 NOT NULL 
- `NStage` VDT_STRING32 NOT NULL 
- `MStage` VDT_STRING32 NOT NULL 
- `SummaryStage` VDT_STRING32 NOT NULL 
- `DateStamp` VDT_DATETIME NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `ctrDiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `CurrentEntry` VDT_STRING10 NOT NULL 
- `CancerDescription` VDT_STRING256 NOT NULL 
- `CancerStatus` VDT_STRING10 NOT NULL 
- `LesionDescription` VDT_STRING100 NOT NULL 
- `LesionOrder` VDT_INT NOT NULL 
- `LesionDimention` VDT_INT NOT NULL 
- `DimLookupID_LesionMeasurable` VDT_SERIALNUMBER NOT NULL 
- `PrimaryCancerID` VDT_INT NOT NULL 
- `PrimaryDiagnosisId` VDT_INT NOT NULL 
- `DateStaged` VDT_DATETIMESTAMP NOT NULL 
- `ctrpt_stage_id` VDT_INT NOT NULL 
- `DimDxSiteID_PrimaryCancerSite` VDT_SERIALNUMBER NOT NULL 
- `PatientCancerStageDateTime` VDT_DATETIME NOT NULL 
- `PtDxOnSetDate` VDT_DATETIME NOT NULL 
- `PtDxLastModifiedDateTime` VDT_DATETIME NOT NULL 
- `PtDxCncrLastModifiedDateTime` VDT_DATETIME NOT NULL 
- `DxSiteDateTime` VDT_DATETIME NOT NULL 
- `IsCancerDx` tinyint NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`
- `DimICDOSiteID` → `DWH.DimICDOSite.DimICDOSiteID`
- `DimCellTypeID` → `DWH.DimCellType.DimCellTypeID`
- `DimLookupID_DiagnosisStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Ranking` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Source` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_HistoricDxFlag` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_CellCategory` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_CellGrade` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Laterality` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Stage` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_StageStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ERStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_PRStatus` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Her2neuMethodType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Her2neuStatusType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Her2neuMethod2Type` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Her2neuStatus2Type` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Recurrence` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_Invasive` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ConfirmedDx` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_DiagnosisType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_DxMethodType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ICDOVersion` → `DWH.DimLookup.DimLookupID`
- `DimDxSiteID_BodySystem` → `DWH.DimDxSite.DimDxSiteID`
- `DimDxSiteID` → `DWH.DimDxSite.DimDxSiteID`
- `DimDateID_DiagnosisStatusDate` → `DWH.DimDate.DimDateID`
- `DimDxSiteID_PrimaryCancerSite` → `DWH.DimDxSite.DimDxSiteID`

---

### DWH.FactPatientEncounter
**Columns:** 35 | **Foreign Keys:** 6

**Columns:**
- `FactPatientEncounterID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimAgendaTemplateGroupTaskID` VDT_SERIALNUMBER NOT NULL 
- `DimAgendaTemplateID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AgendaTask` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_CompletedUser` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_AmendedUser` VDT_SERIALNUMBER NOT NULL 
- `PatientHeaderDescription` VDT_STRING50 NOT NULL 
- `HeaderValidEntryIndicator` VDT_STRING1 NOT NULL 
- `DateOfService` VDT_DATETIME NOT NULL 
- `HeaderTransLogDateTime` VDT_DATETIME NOT NULL 
- `HeaderTransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `PatientHeaderStatus` VDT_STRING1 NOT NULL 
- `CompletedTimeStamp` VDT_DATETIMESTAMP NOT NULL 
- `AmendedTimeStamp` VDT_DATETIMESTAMP NOT NULL 
- `PatientHeaderComment` nvarchar NOT NULL 
- `HeaderRevisionNumber` VDT_INT NOT NULL 
- `PatientAgendaTaskDescription` VDT_STRING50 NOT NULL 
- `PatientTaskSequenceNo` VDT_INT NOT NULL 
- `GroupDescription` VDT_STRING50 NOT NULL 
- `GroupSequenceNumber` VDT_INT NOT NULL 
- `CustomizationXml` VDT_STRING1024 NOT NULL 
- `PatientEncounterStatus` VDT_STRING16 NOT NULL 
- `RequiredIndicator` VDT_STRING1 NOT NULL 
- `PatientAgendaTransLogDateTime` VDT_DATETIME NOT NULL 
- `PatientAgendaTransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `PatientEncounterComment` nvarchar NOT NULL 
- `PatientEncounterRevisionNumber` VDT_INT NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_agenda_hdr_id` VDT_INT NOT NULL 
- `ctrpt_agenda_task_id` VDT_INT NOT NULL 
- `ctrgroup_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimAgendaTemplateID` → `DWH.DimAgendaTemplate.DimAgendaTemplateID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimLookupID_AgendaTask` → `DWH.DimLookup.DimLookupID`
- `DimUserID_CompletedUser` → `DWH.DimUser.DimUserID`
- `DimUserID_AmendedUser` → `DWH.DimUser.DimUserID`

---

### DWH.FactPatientExam
**Columns:** 22 | **Foreign Keys:** 7

**Columns:**
- `FactPatientExamID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_Approved` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ExamApprovedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ExamDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_DictationApprovedDateTime` VDT_SERIALNUMBER NOT NULL 
- `ApprovedIndicator` VDT_STRING1 NOT NULL 
- `ExamValidEntryIndicator` VDT_STRING1 NOT NULL 
- `BodySystemDescription` VDT_STRING30 NOT NULL 
- `ROSPEAssessmentDescription` nvarchar NOT NULL 
- `ExamApprovedDateTime` VDT_DATETIME NOT NULL 
- `ExamDateTime` VDT_DATETIME NOT NULL 
- `DictationApprovedDateTime` VDT_DATETIME NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctrpt_exam_id` VDT_INT NOT NULL 
- `ctrpt_exam_system_id` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ExamSystemValidEntryIndicator` VDT_STRING1 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimUserID` → `DWH.DimUser.DimUserID`
- `DimUserID_Approved` → `DWH.DimUser.DimUserID`
- `DimDateID_ExamApprovedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ExamDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_DictationApprovedDateTime` → `DWH.DimDate.DimDateID`

---

### DWH.FactPatientFamilyHistory
**Columns:** 12 | **Foreign Keys:** 3

**Columns:**
- `FactPatientFamilyHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_FamilyRelationType` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_FamilyMemberDOB` VDT_SERIALNUMBER NOT NULL 
- `AliveIndicator` VDT_STRING1 NOT NULL 
- `AgeAtDeath` VDT_INT NOT NULL 
- `FamilyMemberDOB` VDT_DATETIME NOT NULL 
- `CancerIndicator` VDT_STRING1 NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `ctrFamilyHistoryId` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_FamilyRelationType` → `DWH.DimLookup.DimLookupID`
- `DimDateID_FamilyMemberDOB` → `DWH.DimDate.DimDateID`

---

### DWH.FactPatientImage
**Columns:** 37 | **Foreign Keys:** 8

**Columns:**
- `FactPatientImageID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `DimDoctorID_Oncologist` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ApprovedBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ApprovalDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ImageCreationDate` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ImageStatus` VDT_SERIALNUMBER NOT NULL 
- `Energy` VDT_ENERGY NOT NULL 
- `ImageId` VDT_ID NOT NULL 
- `ImageCreationDate` VDT_DATETIMESTAMP NOT NULL 
- `ImageType` VDT_TABLENAME NOT NULL 
- `ImageStatus` VDT_STRING64 NOT NULL 
- `ApprovalDate` VDT_DATETIME NOT NULL 
- `ImageNote` VDT_TEXT16K NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `IsocenterX` VDT_FLOAT NOT NULL 
- `IsocenterY` VDT_FLOAT NOT NULL 
- `IsocenterZ` VDT_FLOAT NOT NULL 
- `DicomUID` VDT_UID NOT NULL 
- `MetersetExposure` VDT_FLOAT NOT NULL 
- `ExposureTime` VDT_INT NOT NULL 
- `XRayTubeCurrent` VDT_INT NOT NULL 
- `PrimaryDosimeterUnit` VDT_STRING16 NOT NULL 
- `ImageNotesLen` VDT_INT NOT NULL 
- `ctrStudySer` VDT_SERIALNUMBER NOT NULL 
- `ctrSeriesSer` VDT_SERIALNUMBER NOT NULL 
- `ctrSliceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrImageSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `SliceRTType` VDT_TABLENAME NOT NULL 
- `ReferenceImage` VDT_INT NOT NULL 
- `ImageSizeX` VDT_INT NOT NULL 
- `ImageSizeY` VDT_INT NOT NULL 
- `ImageSizeZ` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `DimFieldID` → `DWH.DimField.DimFieldID`
- `DimMachineID` → `DWH.DimMachine.DimMachineID`
- `DimDoctorID_Oncologist` → `DWH.DimDoctor.DimDoctorID`
- `DimUserID_ApprovedBy` → `DWH.DimUser.DimUserID`
- `DimDateID_ApprovalDate` → `DWH.DimDate.DimDateID`
- `DimDateID_ImageCreationDate` → `DWH.DimDate.DimDateID`

---

### DWH.FactPatientLabResult
**Columns:** 49 | **Foreign Keys:** 9

**Columns:**
- `FactPatientLabResultID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_UOM` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_StatusType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AbnormalFlagCode` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_SymbolCode` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ComponentType` VDT_SERIALNUMBER NOT NULL 
- `TypeOfTest` VDT_STRING40 NOT NULL 
- `ComponentName` VDT_STRING60 NOT NULL 
- `TestValue` VDT_FLOAT NOT NULL 
- `MinNorm` VDT_FLOAT NOT NULL 
- `MaxNorm` VDT_FLOAT NOT NULL 
- `TestValueStatusCode` VDT_STRING2 NOT NULL 
- `TestValueStatusDescription` VDT_STRING16 NOT NULL 
- `TestDateTime` VDT_DATETIME NOT NULL 
- `MinReason` VDT_FLOAT NOT NULL 
- `MaxReason` VDT_FLOAT NOT NULL 
- `TestResultApprovedIndicator` VDT_STRING2 NOT NULL 
- `ProducerStakeholderId` VDT_STRING40 NOT NULL 
- `DspRefRange` VDT_STRING40 NOT NULL 
- `PatientId` nchar NOT NULL 
- `TestResultGroupId` VDT_INT NOT NULL 
- `TestId` VDT_INT NOT NULL 
- `PatientVisitId` VDT_INT NOT NULL 
- `TestResultId` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimUserID_Physician` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID_Physician` VDT_SERIALNUMBER NOT NULL 
- `AlertIndicator` VDT_STRING1 NOT NULL 
- `ErroredReason` VDT_STRING256 NOT NULL 
- `AbsoluteMaximum` VDT_FLOAT NOT NULL 
- `AbsoluteMinimum` VDT_FLOAT NOT NULL 
- `TestResultIndicator` VDT_STRING1 NOT NULL 
- `TestResultValue` VDT_STRING256 NOT NULL 
- `TransLogUserId` VDT_STRING256 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedUserId` VDT_STRING256 NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `TestResultValidEntryIndicator` VDT_STRING1 NOT NULL 
- `FacilityGroupName` VDT_STRING60 NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `TestComponentFacilityName` VDT_STRING60 NOT NULL 
- `TestResultComment` nvarchar NOT NULL 
- `ProducerStakeholderName` VDT_STRING128 NOT NULL 
- `TestResultGroupComment` VDT_STRING512 NOT NULL 
- `FacilityCategoryDescritpion` VDT_STRING80 NOT NULL 
- `DimDateID_TestDateTime` VDT_SERIALNUMBER NOT NULL 
- `TestValidEntryIndicator` VDT_STRING1 NOT NULL 
- `ResultApprovedIndicator` VDT_STRING2 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_UOM` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_StatusType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_AbnormalFlagCode` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_SymbolCode` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ComponentType` → `DWH.DimLookup.DimLookupID`
- `DimUserID_Physician` → `DWH.DimUser.DimUserID`
- `DimHospitalDepartmentID_Physician` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`

---

### DWH.FactPatientLabTest
**Columns:** 43 | **Foreign Keys:** 13

**Columns:**
- `FactPatientLabTestID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_SpecimenRejectReason` VDT_SERIALNUMBER NOT NULL 
- `PatientId` nchar NOT NULL 
- `TestId` VDT_INT NOT NULL 
- `PatientVisitId` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `DimLookupID_TestPriority` VDT_SERIALNUMBER NOT NULL 
- `OrderedDateTime` VDT_DATETIME NOT NULL 
- `DimDateID_OrderedDateTime` VDT_SERIALNUMBER NOT NULL 
- `TestRequestedDateTime` VDT_DATETIME NOT NULL 
- `DimDateID_TestRequestedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TestRequestType` VDT_SERIALNUMBER NOT NULL 
- `VerbalOrderId` VDT_INT NOT NULL 
- `SentFlag` VDT_STRING2 NOT NULL 
- `DimUserID_Physician` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID_Physician` VDT_SERIALNUMBER NOT NULL 
- `SpecimenIndicator` VDT_STRING2 NOT NULL 
- `OrderApprovedIndicator` VDT_STRING2 NOT NULL 
- `ResultApprovedIndicator` VDT_STRING2 NOT NULL 
- `CancelIndicator` VDT_STRING2 NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID_Facility` VDT_SERIALNUMBER NOT NULL 
- `FacilityId` VDT_INT NOT NULL 
- `FacilityRequisitionId` VDT_STRING40 NOT NULL 
- `FacilityRequisitionDescription` VDT_STRING80 NOT NULL 
- `TestComment` VDT_STRING NOT NULL 
- `CollectionStartDate` VDT_DATETIME NOT NULL 
- `DimDateID_CollectionStartDate` VDT_SERIALNUMBER NOT NULL 
- `CollectionEndDate` VDT_DATETIME NOT NULL 
- `DimDateID_CollectionEndDate` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_SpecimenAction` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_SpecimenCondCode` VDT_SERIALNUMBER NOT NULL 
- `CollectedBy` VDT_STRING40 NOT NULL 
- `DangerCode` VDT_STRING40 NOT NULL 
- `ReleventClinicalInformation` VDT_STRING NOT NULL 
- `CollectionVolume` VDT_NUMERIC_11_4 NOT NULL 
- `SpecimenSource` VDT_STRING60 NOT NULL 
- `PrimaryDX` VDT_STRING32 NOT NULL 
- `TestOrderComment` VDT_STRING1024 NOT NULL 
- `DimLookupID_CollectionVolumeUnit` VDT_SERIALNUMBER NOT NULL 
- `VitalIndicator` VDT_STRING64 NOT NULL 
- `TestValidEntryIndicator` VDT_STRING1 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_TestPriority` → `DWH.DimLookup.DimLookupID`
- `DimDateID_OrderedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_TestRequestedDateTime` → `DWH.DimDate.DimDateID`
- `DimLookupID_TestRequestType` → `DWH.DimLookup.DimLookupID`
- `DimUserID_Physician` → `DWH.DimUser.DimUserID`
- `DimHospitalDepartmentID_Physician` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimHospitalDepartmentID_Facility` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimDateID_CollectionStartDate` → `DWH.DimDate.DimDateID`
- `DimDateID_CollectionEndDate` → `DWH.DimDate.DimDateID`
- `DimLookupID_SpecimenAction` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_CollectionVolumeUnit` → `DWH.DimLookup.DimLookupID`

---

### DWH.FactPatientMedicalHistory
**Columns:** 46 | **Foreign Keys:** 6

**Columns:**
- `FactPatientMedicalHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_MpauseReasonType` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_DiagnosisDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_MrPapDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_MrMammogramDate` VDT_SERIALNUMBER NOT NULL 
- `ProblemDescription` VDT_STRING256 NOT NULL 
- `DiagnosisDate` VDT_DATETIME NOT NULL 
- `ActiveDiagnosisIndicator` VDT_STRING1 NOT NULL 
- `TreatmentIndicator` VDT_STRING1 NOT NULL 
- `Gravida` VDT_INT NOT NULL 
- `Para` VDT_INT NOT NULL 
- `NoAbortions` VDT_INT NOT NULL 
- `AgeAtFirstBirth` VDT_INT NOT NULL 
- `MensesStartAge` VDT_INT NOT NULL 
- `MpauseCode` VDT_STRING1 NOT NULL 
- `MpauseDescription` VDT_STRING256 NOT NULL 
- `MpauseAge` VDT_INT NOT NULL 
- `OcpUseIndicator` VDT_STRING1 NOT NULL 
- `OcpUseDuration` VDT_INT NOT NULL 
- `MpauseHormoneIndicator` VDT_STRING1 NOT NULL 
- `MpauseHormoneDuration` VDT_INT NOT NULL 
- `OtherHormoneUseIndicator` VDT_STRING1 NOT NULL 
- `OtherHormoneDuration` VDT_INT NOT NULL 
- `MrPapDate` VDT_DATETIME NOT NULL 
- `MrMammogramDate` VDT_DATETIME NOT NULL 
- `CurrentEntryIndicator` VDT_STRING1 NOT NULL 
- `MpauseCycle` VDT_INT NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `ctrPatientMedicalId` VDT_INT NOT NULL 
- `ctrGyneHistoryId` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `MenopauseReason` VDT_STRING256 NOT NULL 
- `GynecHistoryOptionalDetails` VDT_STRING256 NOT NULL 
- `HormonesDescription` VDT_STRING256 NOT NULL 
- `GynecHistoryDetails` VDT_STRING1024 NOT NULL 
- `RecentMammogramComment` VDT_STRING256 NOT NULL 
- `RecentPapSmearComment` VDT_STRING256 NOT NULL 
- `MenstrualDetails` VDT_STRING256 NOT NULL 
- `LatestTestDescription` VDT_STRING256 NOT NULL 
- `MedicalProblemDetails` VDT_STRING1024 NOT NULL 
- `TreatmentDescription` VDT_STRING100 NOT NULL 
- `AgeAtProcedure` VDT_STRING100 NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `MedicalHistoryValidEntryIndicator` VDT_STRING1 NOT NULL 
- `HormoneUseIndicator` VDT_STRING1 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_MpauseReasonType` → `DWH.DimLookup.DimLookupID`
- `DimDateID_DiagnosisDate` → `DWH.DimDate.DimDateID`
- `DimDateID_MrPapDate` → `DWH.DimDate.DimDateID`
- `DimDateID_MrMammogramDate` → `DWH.DimDate.DimDateID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`

---

### DWH.FactPatientMedoncTreatment
**Columns:** 37 | **Foreign Keys:** 5

**Columns:**
- `FactPatientMedoncTreatmentID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimMedoncPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimMedoncPlanPhaseID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentPlanInit` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentPlanEnd` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentStartDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentEndDate` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `TreatmentPlanInitDate` VDT_DATETIME NOT NULL 
- `TreatmentPlanInitTime` VDT_DATETIME NOT NULL 
- `TreatmentPlanEndDate` VDT_DATETIME NOT NULL 
- `TreatmentStartDate` VDT_DATETIME NOT NULL 
- `TreatmentEndDate` VDT_DATETIME NOT NULL 
- `DimUserID_Provider` VDT_SERIALNUMBER NOT NULL 
- `ClinicalTrialTreatmentIndicator` VDT_STRING1 NOT NULL 
- `ClinicalTrialFlag` VDT_STRING1 NOT NULL 
- `NumberOfCycles` VDT_INT NOT NULL 
- `NoOfCyclesCompleted` VDT_INT NOT NULL 
- `CycleLength` VDT_INT NOT NULL 
- `StartCycle` VDT_INT NOT NULL 
- `StartDay` VDT_INT NOT NULL 
- `TreatmentLine` VDT_INT NOT NULL 
- `TreatmentIntent` VDT_STRING40 NOT NULL 
- `TreatmentUse` VDT_STRING40 NOT NULL 
- `TreatmentComments` VDT_STRING1024 NOT NULL 
- `TreatmentModality` VDT_INT NOT NULL 
- `TreatmentDescription` VDT_STRING512 NOT NULL 
- `DiseaseSite` VDT_STRING30 NOT NULL 
- `ctrpt_tx_id` VDT_INT NOT NULL 
- `PtTxLastModifiedDate` VDT_DATETIME NOT NULL 
- `PtTpLastModifiedDate` VDT_DATETIME NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `PtTreatmentIntent` VDT_INT NOT NULL 
- `PtTreatmentUse` VDT_INT NOT NULL 
- `PtTreatmentPlanInitDate` VDT_DATETIME NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimMedoncPlanID` → `DWH.DimMedoncPlan.DimMedoncPlanID`
- `DimMedoncPlanPhaseID` → `DWH.DimMedoncPlanPhase.DimMedoncPlanPhaseID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimUserID_Provider` → `DWH.DimUser.DimUserID`

---

### DWH.FactPatientPayor
**Columns:** 17 | **Foreign Keys:** 2

**Columns:**
- `FactPatientPayorID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimPayorID` VDT_SERIALNUMBER NOT NULL 
- `IsPrimaryPayor` VDT_TINYINT NOT NULL 
- `IsSecondaryPayor` VDT_TINYINT NOT NULL 
- `PayorInsuredName` VDT_NAME NOT NULL 
- `PayorAuthorizationId` VDT_ID NOT NULL 
- `PayorAuthorizationDate` VDT_DATETIME NOT NULL 
- `PayorComment` VDT_COMMENT NOT NULL 
- `PayorPolicyNumber` VDT_ID NOT NULL 
- `PayorRelationshipwithInsured` VDT_NAME NOT NULL 
- `PayorCurrentAccountNumber` VDT_STRING32 NOT NULL 
- `PrcntOfPaymnt` VDT_FLOAT NOT NULL 
- `CoPayment` VDT_MONEY NOT NULL 
- `VerificationDate` VDT_DATETIME NOT NULL 
- `ctrPatientPayorSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimPayorID` → `DWH.DimPayor.DimPayorID`

---

### DWH.FactPatientPrescription
**Columns:** 8 | **Foreign Keys:** 5

**Columns:**
- `FactPatientPrescriptionID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPrescriptionID` VDT_SERIALNUMBER NOT NULL 
- `DimPrescriptionPropertyID` VDT_SERIALNUMBER NOT NULL 
- `DimPrescriptionAnatomyID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `FactPatientDiagnosisID` VDT_SERIALNUMBER NOT NULL 

**Foreign Keys:**
- `DimPrescriptionID` → `DWH.DimPrescription.DimPrescriptionID`
- `DimPrescriptionPropertyID` → `DWH.DimPrescriptionProperty.DimPrescriptionPropertyID`
- `DimPrescriptionAnatomyID` → `DWH.DimPrescriptionAnatomy.DimPrescriptionAnatomyID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`

---

### DWH.FactPatientProcedureHistory
**Columns:** 17 | **Foreign Keys:** 1

**Columns:**
- `FactPatientProcedureHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ProcedureDate` VDT_SERIALNUMBER NOT NULL 
- `ProcedureName` VDT_STRING512 NOT NULL 
- `ProcedureDate` VDT_DATETIME NOT NULL 
- `TreatmentDescription` nvarchar NOT NULL 
- `ProcedureOutCome` nvarchar NOT NULL 
- `AgeAtProcedure` VDT_INT NOT NULL 
- `DiagnosisScheme` VDT_INT NOT NULL 
- `ProcedureValidEntryIndicator` VDT_STRING1 NOT NULL 
- `DateApproxIndicator` VDT_STRING1 NOT NULL 
- `ctrprocedure_id` VDT_INT NOT NULL 
- `ModifiedDateTime` VDT_DATETIME NOT NULL 
- `DiagnosisCode` VDT_STRING20 NOT NULL 
- `SnomedCTCode` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.FactPatientSocialHistory
**Columns:** 15 | **Foreign Keys:** 1

**Columns:**
- `FactPatientSocialHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `NoAlcoholUsePerWeek` VDT_INT NOT NULL 
- `NoAlcoholUsePerDay` VDT_INT NOT NULL 
- `NoPacksPerDay` numeric NOT NULL 
- `NoYearsQuitAlcohol` VDT_INT NOT NULL 
- `NoYearsQuitSmoking` VDT_INT NOT NULL 
- `NoYearsActiveSmoker` VDT_INT NOT NULL 
- `HazardMaterialContactIndicator` VDT_STRING1 NOT NULL 
- `AlcoholUseStatus` VDT_STRING25 NOT NULL 
- `SmokingUseStatus` VDT_STRING25 NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `ctrPatientSocialHistoryId` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.FactPatientStatusIcon
**Columns:** 9 | **Foreign Keys:** 2

**Columns:**
- `FactPatientStatusIconID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimStatusIconID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `ActiveEntryIndicator` VDT_STRING1 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_status_icon_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimStatusIconID` → `DWH.DimStatusIcon.DimStatusIconID`
- `DimPatientID` → `DWH.DimPatient.DimPatientID`

---

### DWH.FactPatientToxicity
**Columns:** 45 | **Foreign Keys:** 14

**Columns:**
- `FactPatientToxicityID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimToxicityGradingCriteriaID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Scheme` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ToxicityCauseCertaintyType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ToxicityCauseType` VDT_SERIALNUMBER NOT NULL 
- `DimDiagnosisCodeID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AssessmentDateTime` VDT_SERIALNUMBER NOT NULL 
- `AssessmentDateTime` VDT_DATETIME NOT NULL 
- `ToxicityGradeAuthour` VDT_INT NOT NULL 
- `ToxicityEffectiveDate` VDT_DATETIME NOT NULL 
- `ToxicityAssessmentType` VDT_STRING100 NOT NULL 
- `ToxicityComponentName` VDT_STRING100 NOT NULL 
- `ToxicitySubcomponentName` VDT_STRING60 NOT NULL 
- `ToxicitySubComponentGradeName` VDT_STRING100 NOT NULL 
- `ToxicityGrade` VDT_INT NOT NULL 
- `AdverseEventsIndicator` VDT_STRING2 NOT NULL 
- `ValidEntryIndicator` VDT_STRING1 NOT NULL 
- `PatientToxicityAssessmentId` VDT_INT NOT NULL 
- `PatientVisitId` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `PatientToxicityAssessmentHeaderId` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `GradePerAssessmentType` VDT_INT NOT NULL 
- `AssessmentType` VDT_INT NOT NULL 
- `ToxicityReason` nvarchar NOT NULL 
- `ToxicityApprovedIndicator` VDT_STRING1 NOT NULL 
- `DimDateID_AssessmentPerformedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ToxicityApprovedDateTime` VDT_SERIALNUMBER NOT NULL 
- `ToxicityReviewRequestIndicator` VDT_STRING1 NOT NULL 
- `ToxicityReviewedIndicator` VDT_STRING1 NOT NULL 
- `DimResourceID_Reviewer` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ToxicityReviewedDateTime` VDT_SERIALNUMBER NOT NULL 
- `ToxicityHeaderValidEntryIndicator` VDT_STRING1 NOT NULL 
- `RevisionNumber` VDT_INT NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AssessmentStartDateTime` VDT_SERIALNUMBER NOT NULL 
- `CorrectedEntryIndicator` VDT_STRING1 NOT NULL 
- `DimDateID_AssessmentEndDateTime` VDT_SERIALNUMBER NOT NULL 
- `AssessmentTypeDesc` VDT_STRING40 NOT NULL 
- `ToxicityApprovedDateTime` VDT_DATETIME NOT NULL 
- `AssessmentPerformedDateTime` VDT_DATETIME NOT NULL 
- `ToxicityReviewedDateTime` VDT_DATETIME NOT NULL 
- `AssessmentStartDateTime` VDT_DATETIME NOT NULL 
- `AssessmentEndDateTime` VDT_DATETIME NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimToxicityGradingCriteriaID` → `DWH.DimToxicityGradingCriteria.DimToxicityGradingCriteriaID`
- `DimLookupID_Scheme` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ToxicityCauseCertaintyType` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_ToxicityCauseType` → `DWH.DimLookup.DimLookupID`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode.DimDiagnosisCodeID`
- `DimDateID_AssessmentDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_AssessmentPerformedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ToxicityApprovedDateTime` → `DWH.DimDate.DimDateID`
- `DimResourceID_Reviewer` → `DWH.DimResource.DimResourceID`
- `DimDateID_ToxicityReviewedDateTime` → `DWH.DimDate.DimDateID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimDateID_AssessmentStartDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_AssessmentEndDateTime` → `DWH.DimDate.DimDateID`

---

### DWH.FactPhysicianOrder
**Columns:** 51 | **Foreign Keys:** 8

**Columns:**
- `FactPhysicianOrderID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AppliedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_AppliedUser` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PhysicianOrderTimeFrame` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_VerbalApproved` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_Verbal` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_Verbal` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_OrderType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TimeFrame` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_OrderCreatedBy` VDT_SERIALNUMBER NOT NULL 
- `AppliedIndicator` VDT_STRING2 NOT NULL 
- `AppliedDateTime` VDT_DATETIME NOT NULL 
- `AppliedText` nvarchar NOT NULL 
- `ApprovedOnFileIndicator` VDT_STRING2 NOT NULL 
- `CancelEntryIndicator` VDT_STRING2 NOT NULL 
- `CompletedIndicator` VDT_STRING2 NOT NULL 
- `GeneratedIndicator` VDT_STRING2 NOT NULL 
- `PlacerOrderNumber` VDT_STRING20 NOT NULL 
- `PlanAffectIndicator` VDT_STRING2 NOT NULL 
- `PhysicianOrderSheetDesc` VDT_STRING100 NOT NULL 
- `PhysicianOrderTimeFrame` VDT_INT NOT NULL 
- `PhysicianOrderTime` VDT_INT NOT NULL 
- `POTimeFrameDateTime` VDT_DATETIME NOT NULL 
- `RecurringIndicator` VDT_STRING2 NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `VerbalOrderValidEntryIndicator` VDT_STRING2 NOT NULL 
- `VerbalOrderApprovalFlag` VDT_STRING2 NOT NULL 
- `VerbalApprovalDateTime` VDT_DATETIME NOT NULL 
- `VerbalApprovalText` nvarchar NOT NULL 
- `VerbalComment` VDT_STRING512 NOT NULL 
- `DisplaySourceType` VDT_STRING20 NOT NULL 
- `VerbalDateTime` VDT_DATETIME NOT NULL 
- `VerbalText` nvarchar NOT NULL 
- `VerbalType` VDT_STRING2 NOT NULL 
- `VerbalTypeDesc` VDT_STRING50 NOT NULL 
- `PhysicianOrderDescription` VDT_STRING256 NOT NULL 
- `PhysicianOrderDetails` VDT_STRING256 NOT NULL 
- `PhysicianOrderCategory` VDT_STRING50 NOT NULL 
- `PhysicianOrderDescText` nvarchar NOT NULL 
- `TreatmentPlanName` VDT_STRING50 NOT NULL 
- `TreatmentPlanVersionNumber` VDT_STRING20 NOT NULL 
- `TreatmentPlanInitDateTime` VDT_DATETIME NOT NULL 
- `ExternalTreatmentPlanName` VDT_STRING100 NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrvrbl_id` VDT_INT NOT NULL 
- `ctrvrbl_order_detail_id` VDT_INT NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimDateID_AppliedDateTime` → `DWH.DimDate.DimDateID`
- `DimUserID_AppliedUser` → `DWH.DimUser.DimUserID`
- `DimDateID_VerbalApproved` → `DWH.DimDate.DimDateID`
- `DimDateID_Verbal` → `DWH.DimDate.DimDateID`
- `DimUserID_Verbal` → `DWH.DimUser.DimUserID`

---

### DWH.FactQuestionnaires
**Columns:** 22 | **Foreign Keys:** 9

**Columns:**
- `FactQuestionnairesID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimQuestionnairesID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID_Approved` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_Author` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_Approved` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ResponseDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ApprovedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_QuestionnaireDateTime` VDT_SERIALNUMBER NOT NULL 
- `PatientResponse` nvarchar NOT NULL 
- `ResponseDateTime` VDT_DATETIME NOT NULL 
- `ResponseValidEntryIndicator` VDT_STRING1 NOT NULL 
- `Status` VDT_STRING1 NOT NULL 
- `ApprovedDateTime` VDT_DATETIME NOT NULL 
- `QuestionnaireDateTime` VDT_DATETIME NOT NULL 
- `ResponseHeaderValidEntryIndicator` VDT_STRING1 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctrqstr_id` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction.DimActivityTransactionID`
- `DimQuestionnairesID` → `DWH.DimQuestionnaires.DimQuestionnairesID`
- `DimHospitalDepartmentID_Approved` → `DWH.DimHospitalDepartment.DimHospitalDepartmentID`
- `DimResourceID_Author` → `DWH.DimResource.DimResourceID`
- `DimUserID_Approved` → `DWH.DimUser.DimUserID`
- `DimDateID_ResponseDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_ApprovedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_QuestionnaireDateTime` → `DWH.DimDate.DimDateID`

---

### DWH.FactRxAdminAgtLevel
**Columns:** 19 | **Foreign Keys:** 1

**Columns:**
- `FactRxAdminAgtLevelID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimRxAgtID` VDT_SERIALNUMBER NOT NULL 
- `ctrRxAdminAgtLevelId` VDT_INT NOT NULL 
- `RxAdminAgtLevelSequence` VDT_INT NOT NULL 
- `RxAdminAgtStartDateID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtEndDateID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtNoDosesTaken` VDT_INT NOT NULL 
- `RxAdminAgtDose` numeric NOT NULL 
- `RxAdminAgtDoseUnit_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtHowRecorded_DimLookupID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtValidEntry` VDT_STRING1 NOT NULL 
- `RxAdminAgtApprovedDatetimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtApprovedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtEnteredby_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtEnteredDatetime` VDT_DATETIME NOT NULL 
- `RxAdminAgtLastModifiedby_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminAgtLastModifiedDatetime` VDT_DATETIME NOT NULL 
- `RxAdminAgtErrorReason` VDT_STRING256 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimRxAgtID` → `DWH.DimRxAgt.DimRxAgtID`

---

### DWH.FactRxAdminDetail
**Columns:** 15 | **Foreign Keys:** 1

**Columns:**
- `FactRxAdminDetailID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimRxAdminID` VDT_SERIALNUMBER NOT NULL 
- `ctrRxAdminDetailId` VDT_INT NOT NULL 
- `RxAdminDetailDatetimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDetailType` VDT_STRING6 NOT NULL 
- `RxAdminDetailDoseTaken` numeric NOT NULL 
- `RxAdminDetailDose` numeric NOT NULL 
- `RxAdminDetailApprDatetimeID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDetailApprovedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDetailValidEntry` VDT_STRING1 NOT NULL 
- `RxAdminDetailEnteredBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDetailEnteredDatetime` VDT_DATETIME NOT NULL 
- `RxAdminDetailLastModifiedBy_DimUserID` VDT_SERIALNUMBER NOT NULL 
- `RxAdminDetailLastModifiedDatetime` VDT_DATETIME NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimRxAdminID` → `DWH.DimRxAdmin.DimRxAdminID`

---

### DWH.FactRxDispSyringe
**Columns:** 11 | **Foreign Keys:** 4

**Columns:**
- `FactRxDispSyringeID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `ctrsyringe_id` VDT_INT NOT NULL 
- `ctrsyringe_seq_no` VDT_INT NOT NULL 
- `RxDispSyringeVolume` numeric NOT NULL 
- `DimLookupID_RxDispSyringeVolumeUnit` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_RxDispSyringeEnteredBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_EnteredDatetime` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_RxDispSyringeLastModifiedBy` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_LastModifiedDatetime` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimLookupID_RxDispSyringeVolumeUnit` → `DWH.DimLookup.DimLookupID`
- `DimUserID_RxDispSyringeEnteredBy` → `DWH.DimUser.DimUserID`
- `DimUserID_RxDispSyringeLastModifiedBy` → `DWH.DimUser.DimUserID`

---

### DWH.FactRxDispensary
**Columns:** 49 | **Foreign Keys:** 1

**Columns:**
- `FactRxDispensaryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimRxAgtID` VDT_SERIALNUMBER NOT NULL 
- `ctrdisp_id` VDT_INT NOT NULL 
- `ctrsyringe_id` VDT_INT NOT NULL 
- `DimDateID_RxDispDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ExpiryDateID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_HydraOverriddenDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_RxDispBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_RxDispEnteredBy` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_RxDispLastModifiedBy` VDT_SERIALNUMBER NOT NULL 
- `DImUserID_RxDispHydraOverriddenBy` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispDosageForm` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispDoseUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispAdminRoute` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispDoseStrengthUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispInfusionType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispInfusionDurationUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispOrderUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispSyringeVolumeUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispAgentVolumeUnit` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_RxDispUnit` VDT_SERIALNUMBER NOT NULL 
- `RxDispEnteredDatetime` VDT_DATETIME NOT NULL 
- `RxDispLastModifiedDatetime` VDT_DATETIME NOT NULL 
- `RxDispComment` VDT_STRING256 NOT NULL 
- `RxDispApproved` VDT_STRING1 NOT NULL 
- `RxDispValidEntry` VDT_STRING1 NOT NULL 
- `RxDispAgentName` VDT_STRING50 NOT NULL 
- `RxDispDispensedDose` numeric NOT NULL 
- `RxDispDispensedDoseRange` numeric NOT NULL 
- `RxDispOrderDose` numeric NOT NULL 
- `RxDispDoseStrength` VDT_STRING15 NOT NULL 
- `RxDispInfusionDuration` VDT_INT NOT NULL 
- `RxDispSyringeQuantity` VDT_INT NOT NULL 
- `RxDispSyringeVolume` numeric NOT NULL 
- `RxDispChangeIndicator` VDT_STRING1 NOT NULL 
- `RxDispAgentVolume` numeric NOT NULL 
- `RxDispHydraDispenseId` VDT_INT NOT NULL 
- `RxDispCourseDescription` VDT_STRING256 NOT NULL 
- `RxDispErrorReason` VDT_STRING256 NOT NULL 
- `RxDispNotDispensedIndicator` VDT_STRING1 NOT NULL 
- `RxDispDispenseQuantity` numeric NOT NULL 
- `RxDispDispenseVolume` numeric NOT NULL 
- `RxDispPlacerOrderNo` VDT_STRING10 NOT NULL 
- `RxDispHydraOverrideReason` VDT_STRING256 NOT NULL 
- `RxDispCustomSyringeIndicator` VDT_STRING1 NOT NULL 
- `RxDispReviewIndicator` VDT_STRING1 NOT NULL 
- `RxDispConcentration` VDT_STRING15 NOT NULL 
- `RxDispFormularyChecked` VDT_STRING1 NOT NULL 
- `LogID` VDT_INT NOT NULL 

**Foreign Keys:**
- `DimRxAgtID` → `DWH.DimRxAgt.DimRxAgtID`

---

### DWH.FactTreatmentHistory
**Columns:** 140 | **Foreign Keys:** 49

**Columns:**
- `FactTreatmentHistoryID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TreatmentIntentType` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_CompletedByUser` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ClinicalStatus` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_PlanStatus` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_StatusUser` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_FieldTechnique` VDT_SERIALNUMBER NOT NULL 
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID1` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID2` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID3` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID4` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID5` VDT_SERIALNUMBER NOT NULL 
- `DimPlanMachineID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_Technique` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TechniqueLabel` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TreatmentDeliveryType` VDT_SERIALNUMBER NOT NULL 
- `DimActualMachineID` VDT_SERIALNUMBER NOT NULL 
- `DimTreatmentTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_UserName1` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_UserName2` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_UserName3` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID1` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID2` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID3` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID4` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID5` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID6` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID7` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID8` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID9` VDT_SERIALNUMBER NOT NULL 
- `DimActualAddOnID10` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_ApprovalUser` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_MachineAuthorization` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedEnergyID` VDT_SERIALNUMBER NOT NULL 
- `DimActualEnergyID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CourseCompletedDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_FirstTreatmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_LastTreatmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PlanApprovedStatusDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AuthorizationDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CorrectionDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentEndTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentRecordDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_TreatmentStartTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_BreakPointDate` VDT_SERIALNUMBER NOT NULL 
- `CompletedDateTime` VDT_DATETIME NOT NULL 
- `FirstTreatmentDate` VDT_DATETIME NOT NULL 
- `LastTreatmentDate` VDT_DATETIME NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `IsActive` VDT_INT NOT NULL 
- `IsBrachy` VDT_INT NOT NULL 
- `PlannedDoseRate` VDT_DOSERATE NOT NULL 
- `PlannedMU` VDT_FLOAT NOT NULL 
- `AuthorizationDate` VDT_DATETIME NOT NULL 
- `DimUserID_AuthorizedBy` VDT_SERIALNUMBER NOT NULL 
- `OverrideParameters` VDT_TYPE NOT NULL 
- `PlannedFieldDose` VDT_FLOAT NOT NULL 
- `DeliveredFieldDose` VDT_FLOAT NOT NULL 
- `CorrectionDateTime` VDT_DATETIME NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `RefPointName` VDT_NAME NOT NULL 
- `DoseCorrectionComment` VDT_COMMENT NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `OtherCourseDoseDelivered` VDT_FLOAT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `TotalDoseLimit` VDT_DOSE NOT NULL 
- `DailyDoseLimit` VDT_DOSE NOT NULL 
- `SessionDoseLimit` VDT_DOSE NOT NULL 
- `BreakPointDate` VDT_DATETIME NOT NULL 
- `BreakPointDose` VDT_DOSE NOT NULL 
- `BreakPointNote` VDT_STRING254 NOT NULL 
- `BreakPointNum` VDT_NUMBER NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `PrimaryFlag` VDT_INT NOT NULL 
- `FractionsDelivered` VDT_INT NOT NULL 
- `FractionsPlanned` VDT_INT NOT NULL 
- `FractionsRemaining` VDT_INT NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `DoseRemainingInFraction` VDT_FLOAT NOT NULL 
- `RunningPartial` VDT_FLOAT NOT NULL 
- `DosePredictedMax` VDT_FLOAT NOT NULL 
- `DosePredictedMin` VDT_FLOAT NOT NULL 
- `DosePredicted` VDT_FLOAT NOT NULL 
- `DosePredictedInOtherCourses` VDT_FLOAT NOT NULL 
- `DoseRemaining` VDT_FLOAT NOT NULL 
- `DoseRemainingMax` VDT_FLOAT NOT NULL 
- `DoseRemainingMin` VDT_FLOAT NOT NULL 
- `ActualDoseRate` VDT_DOSERATE NOT NULL 
- `TreatmentTime` VDT_TIME NOT NULL 
- `DeliveredMU` VDT_FLOAT NOT NULL 
- `DoseDeliveredToPrimaryRefPoint` VDT_FLOAT NOT NULL 
- `PFFlag` VDT_STRING1 NOT NULL 
- `PFMUSubFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PIFlag` VDT_STRING1 NOT NULL 
- `TreatmentEndTime` VDT_DATETIME NOT NULL 
- `TreatmentRecordDateTime` VDT_DATETIME NOT NULL 
- `TreatmentStartTime` VDT_DATETIME NOT NULL 
- `ApprovalDate` VDT_DATETIME NOT NULL 
- `CorrelatedEventNumber` VDT_INT NOT NULL 
- `EventNumber` VDT_INT NOT NULL 
- `FieldMUActual` VDT_FLOAT NOT NULL 
- `FieldStatus` VDT_STRING16 NOT NULL 
- `IntendedNumOfPaintings` VDT_INT NOT NULL 
- `IsImage` VDT_TINYINT NOT NULL 
- `NoFractions` VDT_COUNT NOT NULL 
- `NoOfFractions` VDT_COUNT NOT NULL 
- `NoOfImage` VDT_COUNT NOT NULL 
- `PrintFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `RadiationNumber` VDT_INT NOT NULL 
- `RecordStatus` VDT_STRING16 NOT NULL 
- `RVFlag` VDT_TINYINT NOT NULL 
- `TerminationStatus` VDT_STATUS16 NOT NULL 
- `DistalEndEnergy` VDT_FLOAT NOT NULL 
- `DoseDelta` VDT_DOSE NOT NULL 
- `FractionNumber` VDT_INT NOT NULL 
- `DoseDeliveredPerFraction` VDT_FLOAT NOT NULL 
- `LastChartQADate` VDT_DATETIME NOT NULL 
- `ctrChartQATreatmentSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPhysicianIntentSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointLogSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDoseCorrectionLogSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTechniqueSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientVolumeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointSer` VDT_SERIALNUMBER NOT NULL 
- `ctrBreakPointSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 
- `TreatmentDeliveryType` VDT_STRING16 NOT NULL 
- `TreatmentStartTimeFloatValue` float NOT NULL 
- `NominalEnergy` VDT_ENERGY NOT NULL 
- `DimChartQAID` VDT_SERIALNUMBER NOT NULL 

**Foreign Keys:**
- `DimPatientID` → `DWH.DimPatient.DimPatientID`
- `DimCourseID` → `DWH.DimCourse.DimCourseID`
- `DimLookupID_TreatmentIntentType` → `DWH.DimLookup.DimLookupID`
- `DimUserID_CompletedByUser` → `DWH.DimUser.DimUserID`
- `DimLookupID_ClinicalStatus` → `DWH.DimLookup.DimLookupID`
- `DimPlanID` → `DWH.DimPlan.DimPlanID`
- `DimLookupID_PlanStatus` → `DWH.DimLookup.DimLookupID`
- `DimUserID_StatusUser` → `DWH.DimUser.DimUserID`
- `DimLookupID_FieldTechnique` → `DWH.DimLookup.DimLookupID`
- `DimFieldID` → `DWH.DimField.DimFieldID`
- `DimPlannedAddOnID1` → `DWH.DimAddOn.DimAddOnID`
- `DimPlannedAddOnID2` → `DWH.DimAddOn.DimAddOnID`
- `DimPlannedAddOnID3` → `DWH.DimAddOn.DimAddOnID`
- `DimPlannedAddOnID4` → `DWH.DimAddOn.DimAddOnID`
- `DimPlannedAddOnID5` → `DWH.DimAddOn.DimAddOnID`
- `DimPlanMachineID` → `DWH.DimMachine.DimMachineID`
- `DimLookupID_Technique` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_TechniqueLabel` → `DWH.DimLookup.DimLookupID`
- `DimLookupID_TreatmentDeliveryType` → `DWH.DimLookup.DimLookupID`
- `DimActualMachineID` → `DWH.DimMachine.DimMachineID`
- `DimTreatmentTransactionID` → `DWH.DimTreatmentTransaction.DimTreatmentTransactionID`
- `DimUserID_UserName1` → `DWH.DimUser.DimUserID`
- `DimUserID_UserName2` → `DWH.DimUser.DimUserID`
- `DimUserID_UserName3` → `DWH.DimUser.DimUserID`
- `DimActualAddOnID1` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID2` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID3` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID4` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID5` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID6` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID7` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID8` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID9` → `DWH.DimAddOn.DimAddOnID`
- `DimActualAddOnID10` → `DWH.DimAddOn.DimAddOnID`
- `DimUserID_ApprovalUser` → `DWH.DimUser.DimUserID`
- `DimUserID_MachineAuthorization` → `DWH.DimUser.DimUserID`
- `DimPlannedEnergyID` → `DWH.DimEnergy.DimEnergyID`
- `DimActualEnergyID` → `DWH.DimEnergy.DimEnergyID`
- `DimDateID_CourseCompletedDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_FirstTreatmentDate` → `DWH.DimDate.DimDateID`
- `DimDateID_LastTreatmentDate` → `DWH.DimDate.DimDateID`
- `DimDateID_PlanApprovedStatusDate` → `DWH.DimDate.DimDateID`
- `DimDateID_AuthorizationDate` → `DWH.DimDate.DimDateID`
- `DimDateID_CorrectionDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_TreatmentEndTime` → `DWH.DimDate.DimDateID`
- `DimDateID_TreatmentRecordDateTime` → `DWH.DimDate.DimDateID`
- `DimDateID_TreatmentStartTime` → `DWH.DimDate.DimDateID`
- `DimDateID_BreakPointDate` → `DWH.DimDate.DimDateID`
- `DimUserID_AuthorizedBy` → `DWH.DimUser.DimUserID`

---

### DWH.FactTreatmentHistoryBrachyFlat
**Columns:** 47 | **Foreign Keys:** 0

**Columns:**
- `FactTreatmentHistoryID` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `DimPlanID` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_FieldTechnique` VDT_SERIALNUMBER NOT NULL 
- `DimFieldID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_FirstTreatmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_LastTreatmentDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_PlanApprovedStatusDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AuthorizationDate` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CorrectionDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_TreatmentIntentType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ClinicalStatus` VDT_SERIALNUMBER NOT NULL 
- `FirstTreatmentDate` VDT_DATETIME NOT NULL 
- `LastTreatmentDate` VDT_DATETIME NOT NULL 
- `IsActive` VDT_INT NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `AuthorizationDate` VDT_DATETIME NOT NULL 
- `PlannedFieldDose` VDT_FLOAT NOT NULL 
- `DeliveredFieldDose` VDT_FLOAT NOT NULL 
- `CorrectionDateTime` VDT_DATETIME NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `RefPointName` VDT_NAME NOT NULL 
- `DoseCorrectionComment` VDT_COMMENT NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `OtherCourseDoseDelivered` VDT_FLOAT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `PrimaryFlag` VDT_INT NOT NULL 
- `FractionsDelivered` VDT_INT NOT NULL 
- `FractionsPlanned` VDT_INT NOT NULL 
- `FractionsRemaining` VDT_INT NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `DoseRemainingInFraction` VDT_FLOAT NOT NULL 
- `DoseDelta` VDT_DOSE NOT NULL 
- `TerminationStatus` VDT_STATUS16 NOT NULL 
- `ctrPhysicianIntentSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointLogSer` VDT_SERIALNUMBER NOT NULL 
- `ctrDoseCorrectionLogSer` VDT_SERIALNUMBER NOT NULL 
- `ctrTechniqueSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `ctrRefPointSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.FactVisitNotes
**Columns:** 40 | **Foreign Keys:** 0

**Columns:**
- `FactVisitNoteID` VDT_SERIALNUMBER NOT NULL [PK]
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_VisitNote` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_Signed` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_Approved` VDT_SERIALNUMBER NOT NULL 
- `DimUserID_Override` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_Creator` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_Author` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_AuthorOrg` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_ApprovedBy` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_SupervisedBy` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_SignedBy` VDT_SERIALNUMBER NOT NULL 
- `DimResourceID_Cert` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_NoteType` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_ProfType` VDT_SERIALNUMBER NOT NULL 
- `VisitNoteText` nvarchar NOT NULL 
- `VisitNoteBeginText` VDT_STRING256 NOT NULL 
- `ApprovedFlag` VDT_STRING2 NOT NULL 
- `DictatedFlag` VDT_STRING2 NOT NULL 
- `OverrideText` VDT_STRING256 NOT NULL 
- `ValidIndicator` VDT_STRING2 NOT NULL 
- `PrivateIndicator` VDT_STRING2 NOT NULL 
- `DisciplineType` VDT_STRING60 NOT NULL 
- `GeneratedIndicator` VDT_STRING2 NOT NULL 
- `CompletedIndicator` VDT_STRING2 NOT NULL 
- `RemAttachedIndicator` VDT_STRING2 NOT NULL 
- `BillAccountId` VDT_INT NOT NULL 
- `VisitNoteDateTime` VDT_DATETIME NOT NULL 
- `SignedDateTime` VDT_DATETIME NOT NULL 
- `ApprovedDateTime` VDT_DATETIME NOT NULL 
- `DocumentSer` VDT_INT NOT NULL 
- `TemplateName` VDT_STRING50 NOT NULL 
- `ImgDocumentId` VDT_STRING15 NOT NULL 
- `TransLogDateTime` VDT_DATETIME NOT NULL 
- `TransLogModifiedDateTime` VDT_DATETIME NOT NULL 
- `ctrvisit_note_id` VDT_INT NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.FieldModel
**Columns:** 67 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `CollimatorX1` VDT_COLLPARAM NOT NULL 
- `CollimatorX2` VDT_COLLPARAM NOT NULL 
- `CollimatorY1` VDT_COLLPARAM NOT NULL 
- `CollimatorY2` VDT_COLLPARAM NOT NULL 
- `CouchLat` VDT_COUCHPARAM NOT NULL 
- `CouchLng` VDT_COUCHPARAM NOT NULL 
- `CouchVrt` VDT_COUCHPARAM NOT NULL 
- `CourseId` VDT_ID NOT NULL 
- `CreationDate` VDT_DATETIMESTAMP NOT NULL 
- `DoseRate` VDT_DOSERATE NOT NULL 
- `Energy` VDT_ENERGY NOT NULL 
- `FieldTechnique` VDT_ID NOT NULL 
- `SetupFieldFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `GantryRotation` VDT_ANGLE NOT NULL 
- `GatingFlag` VDT_INT NOT NULL 
- `IsoCenterPositionX` VDT_FLOAT NOT NULL 
- `IsoCenterPositionY` VDT_FLOAT NOT NULL 
- `IsoCenterPositionZ` VDT_FLOAT NOT NULL 
- `LastTreatmentDate` VDT_DATETIME NOT NULL 
- `MachineId` VDT_ID NOT NULL 
- `MachineScale` VDT_SCALE NOT NULL 
- `PatientId` VDT_PATIENTID NOT NULL 
- `PatientSupportAngle` VDT_ANGLE NOT NULL 
- `PlannedMu` VDT_FLOAT NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `PrimaryDosimeterUnit` VDT_ID NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `RadiationName` VDT_NAME NOT NULL 
- `RadiationType` VDT_ENERGYMODE NOT NULL 
- `SetupNote` VDT_STRING254 NOT NULL 
- `SSD` VDT_FLOAT NOT NULL 
- `StopAngle` VDT_ANGLE NOT NULL 
- `ToleranceId` VDT_ID NOT NULL 
- `ToleranceTable` VDT_NAME NOT NULL 
- `TreatmentApprovalState` VDT_STRING64 NOT NULL 
- `AddOnId` VDT_ID NOT NULL 
- `AddOnType` VDT_STRING30 NOT NULL 
- `TotalNumberOfFractionsPlanned` VDT_FLOAT NOT NULL 
- `NoFractionsTreated` VDT_FLOAT NOT NULL 
- `FixLightAzimuthAngle` VDT_ANGLE NOT NULL 
- `FixLightPolarPos` VDT_ANGLE NOT NULL 
- `GantryRtnDirection` VDT_STRING16 NOT NULL 
- `GantryRtnExt` VDT_STRING16 NOT NULL 
- `WedgeDose` VDT_DOSE NOT NULL 
- `RefDose` VDT_DOSE NOT NULL 
- `MLCPlanType` VDT_TABLENAME NOT NULL 
- `IndexParameterType` VDT_TYPE NOT NULL 
- `MURounded` VDT_FLOAT NOT NULL 
- `StructureSetSer` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `CollMode` VDT_COLLMODE NOT NULL 
- `CollRtn` VDT_ANGLE NOT NULL 
- `TreatmentTime` VDT_TIME NOT NULL 
- `IMRTOrRapidArc` VDT_STRING16 NOT NULL 
- `AddOnSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `TechinqueSer` VDT_SERIALNUMBER NOT NULL 
- `ToleranceSer` VDT_SERIALNUMBER NOT NULL 
- `RefImageSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `MachineSer` VDT_SERIALNUMBER NOT NULL 
- `EnergyModeSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `TechniqueSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.FieldModel_FullMig
**Columns:** 12 | **Foreign Keys:** 0

**Columns:**
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `FieldTechnique` VDT_ID NOT NULL 
- `MachineSer` VDT_SERIALNUMBER NOT NULL 
- `DoseRate` VDT_DOSERATE NOT NULL 
- `PlannedMu` VDT_FLOAT NOT NULL 
- `Energy` VDT_ENERGY NOT NULL 
- `RadiationType` VDT_ENERGYMODE NOT NULL 
- `EnergyModeSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `TechniqueSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.ImageModel
**Columns:** 36 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientId` VDT_PATIENTID NOT NULL 
- `MachineId` VDT_ID NOT NULL 
- `FieldId` VDT_ID NOT NULL 
- `FieldName` VDT_NAME NOT NULL 
- `ImageId` VDT_ID NOT NULL 
- `AcquisitionDate` VDT_DATETIMESTAMP NOT NULL 
- `ImageType` VDT_TABLENAME NOT NULL 
- `ImageStatus` VDT_STRING64 NOT NULL 
- `ApprovalDate` VDT_DATETIME NOT NULL 
- `ImageNote` VDT_TEXT16K NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `Oncologist` VDT_SERIALNUMBER NOT NULL 
- `IsocenterX` VDT_FLOAT NOT NULL 
- `IsocenterY` VDT_FLOAT NOT NULL 
- `IsocenterZ` VDT_FLOAT NOT NULL 
- `DicomUID` VDT_UID NOT NULL 
- `Energy` VDT_ENERGY NOT NULL 
- `MetersetExposure` VDT_FLOAT NOT NULL 
- `ExposureTime` VDT_INT NOT NULL 
- `XRayTubeCurrent` VDT_INT NOT NULL 
- `PrimaryDosimeterUnit` VDT_STRING16 NOT NULL 
- `ImageNotesLen` VDT_INT NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `StudySer` VDT_SERIALNUMBER NOT NULL 
- `SeriesSer` VDT_SERIALNUMBER NOT NULL 
- `ImageSer` VDT_SERIALNUMBER NOT NULL 
- `SliceSer` VDT_SERIALNUMBER NOT NULL 
- `ResourceSer` VDT_SERIALNUMBER NOT NULL 
- `SliceRTType` VDT_TABLENAME NOT NULL 
- `ReferenceImage` VDT_INT NOT NULL 
- `ImageSizeX` VDT_INT NOT NULL 
- `ImageSizeY` VDT_INT NOT NULL 
- `ImageSizeZ` VDT_INT NOT NULL 

---

### DWH.MigrationAuditInfo
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `MigrationAuditInfoID` VDT_INT NOT NULL 
- `PackageName` VDT_STRING100 NOT NULL 
- `StartDate` VDT_DATETIME NOT NULL 
- `EndDate` VDT_DATETIME NOT NULL 
- `TotalNoOfRecords` VDT_INT NOT NULL 
- `Status` VDT_INT NOT NULL 

---

### DWH.NLSMetadata
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `TableName` VDT_NAME NOT NULL 
- `ColumnName` VDT_STRING32 NOT NULL 
- `LngColumn` tinyint NOT NULL 

---

### DWH.OverrideModel
**Columns:** 14 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `OverrideParameters` VDT_TYPE NOT NULL 
- `AuthorizationDate` VDT_DATETIME NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_ID NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `DoseDelta` VDT_DOSE NOT NULL 
- `PatientVolumeSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointLogSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.PlanModel
**Columns:** 61 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PlanUID` VDT_UID NOT NULL 
- `NoFractions` VDT_COUNT NOT NULL 
- `TreatmentOrder` VDT_ORDER NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `PlanSetupName` VDT_NAME NOT NULL 
- `TreatmentOrientation` VDT_STRING16 NOT NULL 
- `Status` VDT_STRING64 NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `TreatmentTechnique` VDT_STRING16 NOT NULL 
- `VolumeId` VDT_ID NOT NULL 
- `PrimaryRefPointId` VDT_ID NOT NULL 
- `PrimaryRefPointDelivered` VDT_FLOAT NOT NULL 
- `PrimaryRefPointPlanned` VDT_FLOAT NOT NULL 
- `PrimaryRefPointRemaining` VDT_FLOAT NOT NULL 
- `PrimaryRefPointDeliveredSum` VDT_FLOAT NOT NULL 
- `PrimaryRefPointPlannedSum` VDT_FLOAT NOT NULL 
- `PrimaryRefPointRemainingSum` VDT_FLOAT NOT NULL 
- `NoFractionsPlanned` VDT_INT NOT NULL 
- `NoFractionsRemaining` VDT_INT NOT NULL 
- `NoFractionsTreated` VDT_INT NOT NULL 
- `NoFractionsPlannedSum` VDT_INT NOT NULL 
- `NoFractionsRemainingSum` VDT_INT NOT NULL 
- `NoFractionsTreatedSum` VDT_INT NOT NULL 
- `NoSessionRemaining` VDT_INT NOT NULL 
- `EnergyMode` VDT_STRING1024 NOT NULL 
- `FractionId` VDT_ID NOT NULL 
- `StartDelay` VDT_INT NOT NULL 
- `FractionPatternDigitsPerDay` VDT_INT NOT NULL 
- `FractionPattern` VDT_STRING64 NOT NULL 
- `PredecessorID` VDT_ID NOT NULL 
- `NoSessionPlanned` VDT_INT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `PlanComment` VDT_COMMENT NOT NULL 
- `PlanIntent` VDT_STRING16 NOT NULL 
- `LastDayOfTreatment` VDT_DATETIME NOT NULL 
- `FirstDayOfTreatment` VDT_DATETIME NOT NULL 
- `IsActive` VDT_INT NOT NULL 
- `PatientId` VDT_PATIENTID NOT NULL 
- `Age` VDT_INT NOT NULL 
- `PlanRevision` int NOT NULL 
- `RelationshipType` VDT_STRING16 NOT NULL 
- `RelatedPlanUID` VDT_UID NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_ID NOT NULL 
- `IsBrachy` VDT_INT NOT NULL 
- `IMRTOrRapidArc` VDT_STRING16 NOT NULL 
- `RTTreatmentTechnique` VDT_STRING256 NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RelatedRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSOPClassSer` VDT_SERIALNUMBER NOT NULL 
- `RelatedPlanSOPClassSer` VDT_SERIALNUMBER NOT NULL 
- `PlanRelationshipSer` VDT_SERIALNUMBER NOT NULL 
- `PrimaryRefPointSer` VDT_SERIALNUMBER NOT NULL 
- `FirstRTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `PrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `TreatmentType` VDT_TREATMENTTYPE NOT NULL 

---

### DWH.PlannedAddOn_FullMig
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `AddOnId` VDT_ID NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `Rownum` VDT_SERIALNUMBER NOT NULL 
- `MachineSer` VDT_SERIALNUMBER NOT NULL 
- `DimAddOnID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.RadiationRefPoint
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.RefPointModel
**Columns:** 41 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_ID NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `RefPointName` VDT_NAME NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `OtherCourseDoseDelivered` VDT_FLOAT NOT NULL 
- `DosePredictedInOtherCourses` VDT_FLOAT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `TotalDoseLimit` VDT_DOSE NOT NULL 
- `DailyDoseLimit` VDT_DOSE NOT NULL 
- `SessionDoseLimit` VDT_DOSE NOT NULL 
- `BreakPointDose` VDT_DOSE NOT NULL 
- `BreakPointDate` VDT_DATETIME NOT NULL 
- `BreakPointNote` VDT_STRING254 NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `PrimaryFlag` VDT_INT NOT NULL 
- `FractionsDelivered` VDT_INT NOT NULL 
- `FractionsPlanned` VDT_INT NOT NULL 
- `FractionsRemaining` VDT_INT NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `DoseRemainingInFraction` VDT_FLOAT NOT NULL 
- `RunningPartial` VDT_FLOAT NOT NULL 
- `DoseRemainingMax` VDT_FLOAT NOT NULL 
- `DoseRemainingMin` VDT_FLOAT NOT NULL 
- `DoseRemaining` VDT_FLOAT NOT NULL 
- `DosePredictedMax` VDT_FLOAT NOT NULL 
- `DosePredictedMin` VDT_FLOAT NOT NULL 
- `DosePredicted` VDT_FLOAT NOT NULL 
- `BreakPointNum` VDT_NUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `BreakPointSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.RegistrationModel
**Columns:** 17 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientId` VDT_PATIENTID NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanId` VDT_ID NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `RefImageSer` VDT_SERIALNUMBER NOT NULL 
- `RefImageId` VDT_ID NOT NULL 
- `ApprovalTime` VDT_DATETIME NOT NULL 
- `ApprovalStatus` VDT_STRING64 NOT NULL 
- `MachineId` VDT_ID NOT NULL 
- `RegistrationType` VDT_STRING NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `ResourceSer` VDT_SERIALNUMBER NOT NULL 
- `SeriesSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.TableMetaData
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `TableMetaDataID` VDT_SERIALNUMBER NOT NULL 
- `DimTableName` VDT_STRING512 NOT NULL 
- `TablePrimaryIDColumn` VDT_STRING512 NOT NULL 
- `TableLookupCodeColumn` VDT_STRING512 NOT NULL 
- `TableLookupTypeColumn` VDT_STRING512 NOT NULL 
- `TableColumnToMap` VDT_STRING512 NOT NULL 

---

### DWH.TempDVHDataArray
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `DVHDataArrayID` VDT_SERIALNUMBER NOT NULL 
- `Coverage` float NOT NULL 
- `MaxDose` decimal NOT NULL 
- `MaxDoseUnit` nvarchar NOT NULL 
- `MinDose` decimal NOT NULL 
- `MinDoseUnit` nvarchar NOT NULL 
- `SamplingCoverage` float NOT NULL 
- `StdDev` float NOT NULL 
- `Volume` float NOT NULL 
- `StructureDbKey` VDT_SERIALNUMBER NOT NULL 
- `DVHDataResultID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.TempDVHDataResult
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `DVHDataResultID` VDT_SERIALNUMBER NOT NULL 
- `PatientDbKey` VDT_SERIALNUMBER NOT NULL 
- `CourseDbKey` VDT_SERIALNUMBER NOT NULL 
- `PlanDbKey` VDT_SERIALNUMBER NOT NULL 

---

### DWH.TempDVHPoints
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `DoseValue` float NOT NULL 
- `DoseUnit` nvarchar NOT NULL 
- `Volume` float NOT NULL 
- `VolumeUnit` nvarchar NOT NULL 
- `DVHDataArrayID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.TempFactTreatment2_FullMig
**Columns:** 86 | **Foreign Keys:** 0

**Columns:**
- `DimDateID_CourseCompletedDateTime` varchar NOT NULL 
- `DimDateID_FirstTreatmentDate` varchar NOT NULL 
- `DimDateID_LastTreatmentDate` varchar NOT NULL 
- `DimDateID_PlanApprovedStatusDate` varchar NOT NULL 
- `DimDateID_BreakPointDate` varchar NOT NULL 
- `DimCourseID` VDT_INT NOT NULL 
- `DimLookupID_TreatmentIntentType` VDT_INT NOT NULL 
- `DimUserID_CompletedByUser` VDT_INT NOT NULL 
- `DimLookupID_ClinicalStatus` VDT_INT NOT NULL 
- `CompletedDateTime` VDT_DATETIME NOT NULL 
- `FirstTreatmentDate` datetime NOT NULL 
- `LastTreatmentDate` datetime NOT NULL 
- `DimPlanID` VDT_INT NOT NULL 
- `DimLookupID_PlanStatus` VDT_INT NOT NULL 
- `DimUserID_StatusUser` VDT_INT NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `IsActive` VDT_INT NOT NULL 
- `IsBrachy` VDT_INT NOT NULL 
- `DimLookupID_FieldTechnique` VDT_INT NOT NULL 
- `DimFieldID` VDT_INT NOT NULL 
- `DimPlannedAddOnID1` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID2` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID3` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID4` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID5` VDT_SERIALNUMBER NOT NULL 
- `DimPlanMachineID` VDT_INT NOT NULL 
- `DimPlannedEnergyID` VDT_INT NOT NULL 
- `PlannedDoseRate` VDT_DOSERATE NOT NULL 
- `PlannedMU` VDT_FLOAT NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `RefPointName` VDT_NAME NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `OtherCourseDoseDelivered` VDT_FLOAT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `TotalDoseLimit` VDT_DOSE NOT NULL 
- `DailyDoseLimit` VDT_DOSE NOT NULL 
- `SessionDoseLimit` VDT_DOSE NOT NULL 
- `BreakPointDate` VDT_DATETIME NOT NULL 
- `BreakPointDose` VDT_DOSE NOT NULL 
- `BreakPointNote` VDT_STRING254 NOT NULL 
- `BreakPointNum` VDT_NUMBER NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `PrimaryFlag` VDT_INT NOT NULL 
- `FractionsDelivered` VDT_INT NOT NULL 
- `FractionsPlanned` VDT_INT NOT NULL 
- `FractionsRemaining` VDT_INT NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `DoseRemainingInFraction` VDT_FLOAT NOT NULL 
- `RunningPartial` VDT_FLOAT NOT NULL 
- `DosePredictedMax` VDT_FLOAT NOT NULL 
- `DosePredictedMin` VDT_FLOAT NOT NULL 
- `DosePredicted` VDT_FLOAT NOT NULL 
- `DosePredictedInOtherCourses` VDT_FLOAT NOT NULL 
- `DoseRemaining` VDT_FLOAT NOT NULL 
- `DoseRemainingMax` VDT_FLOAT NOT NULL 
- `DoseRemainingMin` VDT_FLOAT NOT NULL 
- `PhysicianIntentSer` VDT_SERIALNUMBER NOT NULL 
- `MachineSer` VDT_SERIALNUMBER NOT NULL 
- `EnergyModeSer` VDT_SERIALNUMBER NOT NULL 
- `PrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointSer` VDT_SERIALNUMBER NOT NULL 
- `BreakPointSer` VDT_SERIALNUMBER NOT NULL 
- `TechniqueSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_INT NOT NULL 
- `DimDateID_AuthorizationDate` varchar NOT NULL 
- `DimDateID_CorrectionDateTime` varchar NOT NULL 
- `PatientVolumeSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointLogSer` bigint NOT NULL 
- `DoseCorrectionLogSer` bigint NOT NULL 
- `CorrectionNote` VDT_COMMENT NOT NULL 
- `PlannedFieldDose` VDT_FLOAT NOT NULL 
- `DeliveredFieldDose` VDT_FLOAT NOT NULL 
- `CorrectionDateTime` VDT_DATETIME NOT NULL 
- `DimUserID_AuthorizedBy` VDT_INT NOT NULL 
- `AuthorizationDate` VDT_DATETIME NOT NULL 
- `DoseDelta` VDT_DOSE NOT NULL 
- `OverrideParameters` VDT_TYPE NOT NULL 

---

### DWH.TempFactTreatment3_FullMig
**Columns:** 59 | **Foreign Keys:** 0

**Columns:**
- `DimLookupID_Technique` VDT_INT NOT NULL 
- `DimLookupID_TechniqueLabel` VDT_INT NOT NULL 
- `DimLookupID_TreatmentDeliveryType` VDT_INT NOT NULL 
- `DimActualMachineID` VDT_INT NOT NULL 
- `DimActualEnergyID` VDT_INT NOT NULL 
- `DimDateID_TreatmentEndTime` varchar NOT NULL 
- `DimDateID_TreatmentRecordDateTime` varchar NOT NULL 
- `DimDateID_TreatmentStartTime` varchar NOT NULL 
- `DimTreatmentTransactionID` int NOT NULL 
- `DimUserID_UserName1` VDT_INT NOT NULL 
- `DimUserID_UserName2` VDT_INT NOT NULL 
- `DimUserID_UserName3` VDT_INT NOT NULL 
- `DimActualAddOnID1` VDT_INT NOT NULL 
- `DimActualAddOnID2` VDT_INT NOT NULL 
- `DimActualAddOnID3` VDT_INT NOT NULL 
- `DimActualAddOnID4` VDT_INT NOT NULL 
- `DimActualAddOnID5` VDT_INT NOT NULL 
- `DimActualAddOnID6` VDT_INT NOT NULL 
- `DimActualAddOnID7` VDT_INT NOT NULL 
- `DimActualAddOnID8` VDT_INT NOT NULL 
- `DimActualAddOnID9` VDT_INT NOT NULL 
- `DimActualAddOnID10` VDT_INT NOT NULL 
- `DimUserID_ApprovalUser` VDT_INT NOT NULL 
- `DimUserID_MachineAuthorization` VDT_INT NOT NULL 
- `ActualDoseRate` VDT_DOSERATE NOT NULL 
- `TreatmentTime` VDT_TIME NOT NULL 
- `DeliveredMU` VDT_FLOAT NOT NULL 
- `DoseDeliveredToPrimaryRefPoint` VDT_FLOAT NOT NULL 
- `PFFlag` VDT_STRING1 NOT NULL 
- `PFMUSubFlag` tinyint NOT NULL 
- `PIFlag` VDT_STRING1 NOT NULL 
- `TreatmentEndTime` VDT_DATETIME NOT NULL 
- `TreatmentRecordDateTime` VDT_DATETIME NOT NULL 
- `TreatmentStartTime` VDT_DATETIME NOT NULL 
- `ApprovalDate` VDT_DATETIME NOT NULL 
- `CorrelatedEventNumber` VDT_INT NOT NULL 
- `EventNumber` VDT_INT NOT NULL 
- `FieldMUActual` VDT_FLOAT NOT NULL 
- `FieldStatus` VDT_STRING16 NOT NULL 
- `IntendedNumOfPaintings` VDT_INT NOT NULL 
- `IsImage` VDT_FLAG NOT NULL 
- `NoFractions` int NOT NULL 
- `NoOfFractions` int NOT NULL 
- `NoOfImage` int NOT NULL 
- `PrintFlag` int NOT NULL 
- `RadiationNumber` VDT_INT NOT NULL 
- `RecordStatus` VDT_STRING16 NOT NULL 
- `RVFlag` tinyint NOT NULL 
- `TerminationStatus` VDT_STATUS16 NOT NULL 
- `DistalEndEnergy` VDT_FLOAT NOT NULL 
- `FractionNumber` VDT_INT NOT NULL 
- `LastChartQADate` VDT_DATETIMESTAMP NOT NULL 
- `ctrChartQATreatmentSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` bigint NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `DoseDeliveredPerFraction` VDT_FLOAT NOT NULL 

---

### DWH.TempFactTreatmentBrachy_FullMig
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `OtherCourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseStartDateTime` VDT_DATETIME NOT NULL 
- `CourseCompletedDateTime` VDT_DATETIME NOT NULL 

---

### DWH.TempFactTreatment_FullMig
**Columns:** 73 | **Foreign Keys:** 0

**Columns:**
- `DimDateID_CourseCompletedDateTime` varchar NOT NULL 
- `DimDateID_FirstTreatmentDate` varchar NOT NULL 
- `DimDateID_LastTreatmentDate` varchar NOT NULL 
- `DimDateID_PlanApprovedStatusDate` varchar NOT NULL 
- `DimDateID_BreakPointDate` varchar NOT NULL 
- `DimCourseID` VDT_INT NOT NULL 
- `DimLookupID_TreatmentIntentType` VDT_INT NOT NULL 
- `DimUserID_CompletedByUser` VDT_INT NOT NULL 
- `DimLookupID_ClinicalStatus` VDT_INT NOT NULL 
- `CompletedDateTime` VDT_DATETIME NOT NULL 
- `FirstTreatmentDate` datetime NOT NULL 
- `LastTreatmentDate` datetime NOT NULL 
- `DimPlanID` VDT_INT NOT NULL 
- `DimLookupID_PlanStatus` VDT_INT NOT NULL 
- `DimUserID_StatusUser` VDT_INT NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `IsActive` VDT_INT NOT NULL 
- `IsBrachy` VDT_INT NOT NULL 
- `DimLookupID_FieldTechnique` VDT_INT NOT NULL 
- `DimFieldID` VDT_INT NOT NULL 
- `DimPlannedAddOnID1` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID2` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID3` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID4` VDT_SERIALNUMBER NOT NULL 
- `DimPlannedAddOnID5` VDT_SERIALNUMBER NOT NULL 
- `DimPlanMachineID` VDT_INT NOT NULL 
- `DimPlannedEnergyID` VDT_INT NOT NULL 
- `PlannedDoseRate` VDT_DOSERATE NOT NULL 
- `PlannedMU` VDT_FLOAT NOT NULL 
- `RefPointId` VDT_ID NOT NULL 
- `RefPointName` VDT_NAME NOT NULL 
- `CourseDoseDelivered` VDT_FLOAT NOT NULL 
- `CourseDosePlanned` VDT_FLOAT NOT NULL 
- `CourseDoseRemaining` VDT_FLOAT NOT NULL 
- `OtherCourseDoseDelivered` VDT_FLOAT NOT NULL 
- `DoseCorrection` VDT_FLOAT NOT NULL 
- `TotalDoseLimit` VDT_DOSE NOT NULL 
- `DailyDoseLimit` VDT_DOSE NOT NULL 
- `SessionDoseLimit` VDT_DOSE NOT NULL 
- `BreakPointDate` VDT_DATETIME NOT NULL 
- `BreakPointDose` VDT_DOSE NOT NULL 
- `BreakPointNote` VDT_STRING254 NOT NULL 
- `BreakPointNum` VDT_NUMBER NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 
- `PrimaryFlag` VDT_INT NOT NULL 
- `FractionsDelivered` VDT_INT NOT NULL 
- `FractionsPlanned` VDT_INT NOT NULL 
- `FractionsRemaining` VDT_INT NOT NULL 
- `DosePerFraction` VDT_DOSE NOT NULL 
- `DoseDelivered` VDT_FLOAT NOT NULL 
- `DoseRemainingInFraction` VDT_FLOAT NOT NULL 
- `RunningPartial` VDT_FLOAT NOT NULL 
- `DosePredictedMax` VDT_FLOAT NOT NULL 
- `DosePredictedMin` VDT_FLOAT NOT NULL 
- `DosePredicted` VDT_FLOAT NOT NULL 
- `DosePredictedInOtherCourses` VDT_FLOAT NOT NULL 
- `DoseRemaining` VDT_FLOAT NOT NULL 
- `DoseRemainingMax` VDT_FLOAT NOT NULL 
- `DoseRemainingMin` VDT_FLOAT NOT NULL 
- `PhysicianIntentSer` VDT_SERIALNUMBER NOT NULL 
- `MachineSer` VDT_SERIALNUMBER NOT NULL 
- `EnergyModeSer` VDT_SERIALNUMBER NOT NULL 
- `PrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `RefPointSer` VDT_SERIALNUMBER NOT NULL 
- `BreakPointSer` VDT_SERIALNUMBER NOT NULL 
- `TechniqueSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_INT NOT NULL 

---

### DWH.TempResourceStkh
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAppUserSer` VDT_SERIALNUMBER NOT NULL 
- `ctruserid` nvarchar NOT NULL 
- `ctrstkh_id` nvarchar NOT NULL 
- `ctrinst_id` nvarchar NOT NULL 

---

### DWH.TempUpgdDimPrescription
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `LinkedPlans` VDT_STRING256 NOT NULL 

---

### DWH.Temp_DataReconciliation
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `TableName` sysname NOT NULL 
- `TotalRecords` int NOT NULL 

---

### DWH.TempstgDimPatient
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `pt_id` VDT_STRING20 NOT NULL 
- `IsDuplicatePatientSer` int NOT NULL 
- `Id` int NOT NULL [PK]

---

### DWH.TempstgDimPatientAdmissionStatus
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `HospitalSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `DepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `PatientHospitalRevCount` VDT_REVISIONCOUNT NOT NULL 
- `PatientDepartmentDefaultFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `StartDateTime` VDT_DATETIME NOT NULL 
- `EndDateTime` VDT_DATETIME NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `InPatientFlag` int NOT NULL 

---

### DWH.TempstgDimPatientSocialHstry
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `NoPacksPerDay` numeric NOT NULL 
- `AlcoholUseStatus` VDT_STRING25 NOT NULL 
- `SmokingUseStatus` VDT_STRING25 NOT NULL 
- `ctrPatientSocialHistoryId` VDT_INT NOT NULL 
- `TransLogMTstamp` datetime NOT NULL 

---

### DWH.TempstgMOPatientEmergencyContact
**Columns:** 9 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `PatientEmergencyContactAddress` VDT_STRING512 NOT NULL 
- `PatientEmergencyContactComment` VDT_COMMENT NOT NULL 
- `PatientEmergencyContactEntrusted` VDT_NUMBER NOT NULL 
- `PatientEmergencyContactFullName` VDT_STRING256 NOT NULL 
- `PatientEmergencyContactHomePhone` VDT_PHONENUMBER NOT NULL 
- `PatientEmergencyContactMobilePhone` VDT_PHONENUMBER NOT NULL 
- `PatientEmergencyContactWorkPhone` VDT_PHONENUMBER NOT NULL 
- `PatientEmergencyContactRelationship` VDT_STRING64 NOT NULL 

---

### DWH.TreatmentHstryModel
**Columns:** 189 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientId` VDT_PATIENTID NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `CourseId` VDT_ID NOT NULL 
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `PlanSetupId` VDT_ID NOT NULL 
- `RadiationSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationId` VDT_ID NOT NULL 
- `RadiationName` VDT_NAME NOT NULL 
- `ToleranceName` VDT_NAME NOT NULL 
- `PlanSetupStatus` VDT_STRING64 NOT NULL 
- `Scale` VDT_SCALE NOT NULL 
- `MachineId` VDT_ID NOT NULL 
- `Energy` VDT_ENERGY NOT NULL 
- `IsoCenterPositionX` VDT_FLOAT NOT NULL 
- `IsoCenterPositionY` VDT_FLOAT NOT NULL 
- `IsoCenterPositionZ` VDT_FLOAT NOT NULL 
- `SetupNote` VDT_STRING254 NOT NULL 
- `FieldTechnique` VDT_ID NOT NULL 
- `FieldType` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `PlannedMU` VDT_FLOAT NOT NULL 
- `TreatmentTime` VDT_TIME NOT NULL 
- `HistoryNote` VDT_STRING1024 NOT NULL 
- `DeliveredMU` VDT_FLOAT NOT NULL 
- `DoseDeliveredToPrimaryRefPoint` VDT_FLOAT NOT NULL 
- `FractionNumber` VDT_INT NOT NULL 
- `TreatmentRecordSer` VDT_SERIALNUMBER NOT NULL 
- `CouchLat` VDT_COUCHPARAM NOT NULL 
- `CouchLatIso` VDT_COUCHPARAM NOT NULL 
- `CouchLatOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchLatPlanned` VDT_COUCHPARAM NOT NULL 
- `CouchLng` VDT_COUCHPARAM NOT NULL 
- `CouchLngIso` VDT_COUCHPARAM NOT NULL 
- `CouchLngOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchLngPlanned` VDT_COUCHPARAM NOT NULL 
- `CouchVrt` VDT_COUCHPARAM NOT NULL 
- `CouchVrtIso` VDT_COUCHPARAM NOT NULL 
- `CouchVrtOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchVrtPlanned` VDT_COUCHPARAM NOT NULL 
- `EnergyModeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `MetersetOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `NominalEnergy` VDT_ENERGY NOT NULL 
- `PFFlag` VDT_STRING1 NOT NULL 
- `PFMUSubFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PIFlag` VDT_STRING1 NOT NULL 
- `PatSupPitchOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PatSupRollOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `PatSupportPitchAngle` VDT_ANGLE NOT NULL 
- `PatSupportRollAngle` VDT_ANGLE NOT NULL 
- `PatientSupportAngle` VDT_ANGLE NOT NULL 
- `PatientSupportAngleOverFlag` VDT_OVERRIDEFLAG NOT NULL 
- `SSD` VDT_FLOAT NOT NULL 
- `SSDOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TreatmentRecordDateTime` VDT_DATETIME NOT NULL 
- `TreatmentStartTime` VDT_DATETIME NOT NULL 
- `TreatmentEndTime` VDT_DATETIME NOT NULL 
- `RadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `ToleranceSer` bigint NOT NULL 
- `EnergyModeSer` bigint NOT NULL 
- `ActualCollMode` VDT_COLLMODE NOT NULL 
- `BeamCurrentModulationId` VDT_ID NOT NULL 
- `BeamModifiersSet` VDT_NAME NOT NULL 
- `BeamOffCode` VDT_STRING64 NOT NULL 
- `CollMode` VDT_COLLMODE NOT NULL 
- `CollModeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollRtn` VDT_ANGLE NOT NULL 
- `CollRtnOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollX1` VDT_COLLPARAM NOT NULL 
- `CollX1OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollX2` VDT_COLLPARAM NOT NULL 
- `CollX2OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollY1` VDT_COLLPARAM NOT NULL 
- `CollY1OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CollY2` VDT_COLLPARAM NOT NULL 
- `CollY2OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `CouchCorrectionLat` VDT_COUCHPARAM NOT NULL 
- `CouchCorrectionLng` VDT_COUCHPARAM NOT NULL 
- `CouchCorrectionVrt` VDT_COUCHPARAM NOT NULL 
- `DoseRateOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `GantryRtnOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 
- `HstryTaskName` VDT_TASKNAME NOT NULL 
- `LastCorrelatedEventNumber` VDT_INT NOT NULL 
- `LastEventNumber` VDT_INT NOT NULL 
- `LastFractionNumber` VDT_INT NOT NULL 
- `LastFractionNumberCalc` VDT_INT NOT NULL 
- `MachOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `MUpDeg` VDT_MUDEG NOT NULL 
- `MUpDegOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `NumOfPaintOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `OffPlaneAngle` VDT_ANGLE NOT NULL 
- `OverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `RadiationHstryType` VDT_TYPE NOT NULL 
- `SnoutPosition` VDT_DISTANCE NOT NULL 
- `SnoutPosOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `SOBPWidth` VDT_FLOAT NOT NULL 
- `StopAngle` VDT_ANGLE NOT NULL 
- `StructureSetUID` VDT_UID NOT NULL 
- `TableTopEccAngleOverFlag` VDT_OVERRIDEFLAG NOT NULL 
- `TableTopEccentricAngle` VDT_ANGLE NOT NULL 
- `TreatmentRecordSOPClassSer` bigint NOT NULL 
- `TreatmentRecordUID` VDT_UID NOT NULL 
- `TreatmentTimeOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `WedgeAngle` VDT_ANGLE NOT NULL 
- `WedgeAngle2` VDT_ANGLE NOT NULL 
- `WedgeDirection` VDT_FLOAT NOT NULL 
- `WedgeDirection2` VDT_FLOAT NOT NULL 
- `WedgeDoseOverrideFlag` VDT_OVERRIDEFLAG NOT NULL 
- `WedgeNumber1` VDT_NUMBER NOT NULL 
- `WedgeNumber2` VDT_NUMBER NOT NULL 
- `ActualDoseRate` VDT_DOSERATE NOT NULL 
- `ApprovalDate` VDT_DATETIME NOT NULL 
- `DistalEndEnergy` VDT_FLOAT NOT NULL 
- `CorrelatedEventNumber` VDT_INT NOT NULL 
- `EventNumber` VDT_INT NOT NULL 
- `FieldMUActual` VDT_FLOAT NOT NULL 
- `FieldSetupNote` VDT_STRING1024 NOT NULL 
- `FieldStatus` VDT_STRING16 NOT NULL 
- `IsImage` VDT_FLAG NOT NULL 
- `NoFractions` VDT_COUNT NOT NULL 
- `NoOfFractions` VDT_COUNT NOT NULL 
- `NoOfImage` VDT_COUNT NOT NULL 
- `PrintFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `PSACorrection` VDT_ANGLE NOT NULL 
- `RadiationNumber` VDT_INT NOT NULL 
- `RadiationType` VDT_ENERGYMODE NOT NULL 
- `RecordStatus` VDT_STRING16 NOT NULL 
- `RVFlag` VDT_TINYINT NOT NULL 
- `SeriesSer` bigint NOT NULL 
- `UserName1` VDT_NAME NOT NULL 
- `RefPointSer` bigint NOT NULL 
- `Technique` VDT_TECHNIQUE NOT NULL 
- `TechniqueLabel` VDT_STRING64 NOT NULL 
- `TreatmentDeliveryType` VDT_STRING16 NOT NULL 
- `IntendedNumOfPaintings` VDT_INT NOT NULL 
- `FirstRTPlanSer` bigint NOT NULL 
- `FirstPlanSetupSer` bigint NOT NULL 
- `RTPlanSer` bigint NOT NULL 
- `PlanUID` VDT_UID NOT NULL 
- `RTPlanAge` int NOT NULL 
- `ActualMachineSer` bigint NOT NULL 
- `ActualMachineAuthorization` VDT_NAME NOT NULL 
- `AddOnId1` nvarchar NOT NULL 
- `AddOnId10` nvarchar NOT NULL 
- `AddOnId2` nvarchar NOT NULL 
- `AddOnId3` nvarchar NOT NULL 
- `AddOnId4` nvarchar NOT NULL 
- `AddOnId5` nvarchar NOT NULL 
- `AddOnId6` nvarchar NOT NULL 
- `AddOnId7` nvarchar NOT NULL 
- `AddOnId8` nvarchar NOT NULL 
- `AddOnId9` nvarchar NOT NULL 
- `AddOnSubType1` VDT_STRING64 NOT NULL 
- `AddOnSubType10` VDT_STRING64 NOT NULL 
- `AddOnSubType2` VDT_STRING64 NOT NULL 
- `AddOnSubType3` VDT_STRING64 NOT NULL 
- `AddOnSubType4` VDT_STRING64 NOT NULL 
- `AddOnSubType5` VDT_STRING64 NOT NULL 
- `AddOnSubType6` VDT_STRING64 NOT NULL 
- `AddOnSubType7` VDT_STRING64 NOT NULL 
- `AddOnSubType8` VDT_STRING64 NOT NULL 
- `AddOnSubType9` VDT_STRING64 NOT NULL 
- `AddOnType1` nvarchar NOT NULL 
- `AddOnType10` nvarchar NOT NULL 
- `AddOnType2` nvarchar NOT NULL 
- `AddOnType3` nvarchar NOT NULL 
- `AddOnType4` nvarchar NOT NULL 
- `AddOnType5` nvarchar NOT NULL 
- `AddOnType6` nvarchar NOT NULL 
- `AddOnType7` nvarchar NOT NULL 
- `AddOnType8` nvarchar NOT NULL 
- `AddOnType9` nvarchar NOT NULL 
- `FileName` VDT_FILENAME NOT NULL 
- `FixLightAzimuthAngle` VDT_ANGLE NOT NULL 
- `FixLightPolarPos` VDT_ANGLE NOT NULL 
- `GantryRtn` VDT_ANGLE NOT NULL 
- `GantryRtnDirection` VDT_STRING16 NOT NULL 
- `GantryRtnExt` VDT_STRING16 NOT NULL 
- `MachineNote` VDT_STRING1024 NOT NULL 
- `PlanSOPClassSer` bigint NOT NULL 
- `ResourceSer` bigint NOT NULL 
- `TerminationStatus` VDT_STATUS16 NOT NULL 
- `WedgeDose` VDT_DOSE NOT NULL 
- `TechniqueSer` bigint NOT NULL 
- `PlannedGantryRtnExt` VDT_STRING16 NOT NULL 
- `PlannedCollMode` VDT_COLLMODE NOT NULL 
- `PlannedWedgeDose` VDT_DOSE NOT NULL 
- `DoseDeliveredPerFraction` VDT_FLOAT NOT NULL 

---

### DWH.UpgradeMigrationAuditInfo
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `UpgradeMigrationAuditInfo` VDT_INT NOT NULL 
- `PackageName` VDT_STRING100 NOT NULL 
- `StartDate` VDT_DATETIME NOT NULL 
- `EndDate` VDT_DATETIME NOT NULL 
- `Status` VDT_INT NOT NULL 

---

### DWH.UpgradeParallelPackageDependant
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `UpgradeRuleID` int NOT NULL 
- `DependantRuleID` int NOT NULL 

---

### DWH.stgAccountBillingCodeDetails
**Columns:** 8 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_SERIALNUMBER NOT NULL 
- `ctrAccountBillingCodeSer` VDT_SERIALNUMBER NOT NULL 
- `AccountBillingCode` VDT_STRING128 NOT NULL 
- `AccountBillingCodeStartDate` VDT_DATETIME NOT NULL 
- `AccountBillingCodeEndDate` VDT_DATETIME NOT NULL 
- `AccountBillingCodeObjectStatus` VDT_STRING16 NOT NULL 
- `AccountBillingCodeValidEntryInd` VDT_STRING1 NOT NULL 
- `AccountBillingCodeInPatientFlag` VDT_INT NOT NULL 

---

### DWH.stgAllTreatmentChanges
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` VDT_INT NOT NULL 

---

### DWH.stgAllTreatmentChangesPatientSer
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgConsTreatmentHistory
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgCourseDiagnosisKeys
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgCourseModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` bigint NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgDeletedActivityInstanceLink
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `ActivityInstanceLinkSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActTransDerivedUpdate
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `DxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 
- `DerivedAppointmentTaskDate` VDT_DATETIME NOT NULL 
- `ActivityOwnerFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 

---

### DWH.stgDimActTransDerivedUpdate_MO
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `DxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActTransDimResourceID
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `AppointmentResourceStatus` VDT_STRING64 NOT NULL 
- `ResourceType` VDT_STRING64 NOT NULL 
- `IsGroupResource` VDT_STRING2 NOT NULL 

---

### DWH.stgDimActivityTransaction
**Columns:** 18 | **Foreign Keys:** 0

**Columns:**
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_CreationDate` VDT_SERIALNUMBER NOT NULL 
- `AppointmentInstanceFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `ActivityStartDateTime` VDT_DATETIME NOT NULL 
- `ActivityEndDateTime` VDT_DATETIME NOT NULL 
- `ScheduledEndTime` VDT_DATETIME NOT NULL 
- `AppointmentDateTime` VDT_DATETIME NOT NULL 
- `DimDateID_ScheduledEndTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_AppointmentDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ActivityStartDateTime` VDT_SERIALNUMBER NOT NULL 
- `DimDateID_ActivityEndDateTime` VDT_SERIALNUMBER NOT NULL 
- `DerivedAppointmentTaskDate` VDT_DATETIME NOT NULL 
- `AppointmentStatus` VDT_STRING64 NOT NULL 
- `AppointmentResourceStatus` VDT_STRING64 NOT NULL 
- `DimLookupID_AppointmentResourceStatus` VDT_SERIALNUMBER NOT NULL 
- `DimLookupID_AppointmentStatus` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransactionActivityCompletedBy
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `Rno` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransactionActivityCreatedBy
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `Rno` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransactionCheckedIn
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `Rno` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `CheckedIn` VDT_STRING1 NOT NULL 
- `IsScheduled` VDT_STRING1 NOT NULL 

---

### DWH.stgDimActivityTransactionDimHospDeptID
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `Rno` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransactionDimResourceID_MO
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctrpt_visit_id` VDT_INT NOT NULL 
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `DimResourceID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransactionForDimActivityID
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 
- `ActivityRevCount` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransactionHistory
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimActivityTransaction_MO
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `pt_id` VDT_STRING20 NOT NULL 
- `pt_visit_id` VDT_INT NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `GhostActivityFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 

---

### DWH.stgDimAddOn
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `AddOnSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimAgendaTemplateGroupTask
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ctrinst_id` VDT_STRING60 NOT NULL 
- `ctragenda_template_id` VDT_INT NOT NULL 
- `ctragenda_template_task_id` VDT_INT NOT NULL 

---

### DWH.stgDimAgendaTemplateGroupTaskDel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ctrinst_id` VDT_STRING60 NOT NULL 
- `ctragenda_template_id` VDT_INT NOT NULL 
- `ctragenda_template_task_id` VDT_INT NOT NULL 

---

### DWH.stgDimBrachyApplicator
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `ctrBrachyApplicatorSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimBrachyApplicator_UPD
**Columns:** 23 | **Foreign Keys:** 0

**Columns:**
- `DimBrachyApplicatorID` VDT_SERIALNUMBER NOT NULL 
- `BrachyApplicatorId` VDT_ID NOT NULL 
- `BrachyApplicatorName` VDT_NAME NOT NULL 
- `BrachyApplicatorTypeInfo` VDT_STRING16 NOT NULL 
- `DefaultLength` VDT_FLOAT NOT NULL 
- `ManufacturerName` VDT_STRING254 NOT NULL 
- `NoOfShapePoints` VDT_INT NOT NULL 
- `Shape` VDT_CONTOURPOINTS NOT NULL 
- `NoOfSourceGeom` VDT_INT NOT NULL 
- `SourceGeometry` image NOT NULL 
- `WallMaterialId` VDT_STRING16 NOT NULL 
- `WallNominalTransmission` VDT_FLOAT NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `StepSize` VDT_FLOAT NOT NULL 
- `FirstSourcePosition` VDT_FLOAT NOT NULL 
- `LastSourcePosition` VDT_FLOAT NOT NULL 
- `SeparateSources` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `DefaultChannelNumber` VDT_INT NOT NULL 
- `DimUserID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIMESTAMP NOT NULL 
- `DeadSpace` VDT_FLOAT NOT NULL 
- `ctrBrachyApplicatorSer` VDT_SERIALNUMBER NOT NULL 
- `LogID` VDT_INT NOT NULL 

---

### DWH.stgDimChannel
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `ctrChannelSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimDoctor
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `DimLookupID_ResourceType` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 

---

### DWH.stgDimEnergy
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `DimMachineID` VDT_SERIALNUMBER NOT NULL 
- `ctrEnergyModeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimLookupCellCategory
**Columns:** 14 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_BIGNUMBER NOT NULL 
- `TableName` VDT_NAME NOT NULL 
- `LookupCode` VDT_STRING64 NOT NULL 
- `LookupType` VDT_INT NOT NULL 
- `SubSelector` VDT_SERIALNUMBER NOT NULL 
- `LookupDescriptionENU` VDT_STRING256 NOT NULL 
- `LookupDescriptionFRA` VDT_STRING256 NOT NULL 
- `LookupDescriptionESN` VDT_STRING256 NOT NULL 
- `LookupDescriptionCHS` VDT_STRING256 NOT NULL 
- `LookupDescriptionDEU` VDT_STRING256 NOT NULL 
- `LookupDescriptionITA` VDT_STRING256 NOT NULL 
- `LookupDescriptionJPN` VDT_STRING256 NOT NULL 
- `LookupDescriptionPTB` VDT_STRING256 NOT NULL 
- `LookupDescriptionSVE` VDT_STRING256 NOT NULL 

---

### DWH.stgDimMachineBrachyUpd
**Columns:** 15 | **Foreign Keys:** 0

**Columns:**
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `RadiationDeviceType` VDT_TABLENAME NOT NULL 
- `MaxDwellTimePerChannel` VDT_FLOAT NOT NULL 
- `MaxDwellTimePerPos` VDT_FLOAT NOT NULL 
- `MaxDwellTimePerTreatment` VDT_FLOAT NOT NULL 
- `TimeResolution` VDT_FLOAT NOT NULL 
- `SourceMovementType` VDT_STRING16 NOT NULL 
- `MinStepSize` VDT_FLOAT NOT NULL 
- `MaxStepSize` VDT_FLOAT NOT NULL 
- `NumOfDwellPosPerChannel` VDT_INT NOT NULL 
- `StepSizeResolution` VDT_FLOAT NOT NULL 
- `PosToSourceDist` VDT_FLOAT NOT NULL 
- `DoseRateMode` VDT_STRING16 NOT NULL 
- `DimLookupID_RadiationDeviceType` VDT_SERIALNUMBER NOT NULL 
- `BrachyExportPostProcessor` VDT_STRING254 NOT NULL 

---

### DWH.stgDimPatientAdmission_HstryDateTime
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `HospitalSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientHospitalRevCount` VDT_REVISIONCOUNT NOT NULL 
- `DepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `HstryDateTime` VDT_DATETIME NOT NULL 

---

### DWH.stgDimPatientAdmission_InPatientFlag
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `HospitalSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientHospitalRevCount` VDT_REVISIONCOUNT NOT NULL 
- `DepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 
- `InPatientFlag` int NOT NULL 

---

### DWH.stgDimPatientDeathStatus_MO
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `PatientDeathStatus` VDT_STRING10 NOT NULL 

---

### DWH.stgDimPatientDeathStatus_RO
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientDeathStatus` VDT_STRING10 NOT NULL 

---

### DWH.stgDimPatientDepartment
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_BIGNUMBER NOT NULL 
- `ctrPatientDepartmentSer` VDT_SERIALNUMBER NOT NULL 
- `DefaultFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `ObjectStatus` VDT_OBJECTSTATUS NOT NULL 

---

### DWH.stgDimPatientEmergencyContactFullName_MO
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `PatientEmergencyContactFullName` VDT_STRING256 NOT NULL 

---

### DWH.stgDimPatientEmergencyContactFullName_RO
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PatientEmergencyContactFullName` VDT_STRING512 NOT NULL 

---

### DWH.stgDimPatientPhoto
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PhotoSer` VDT_SERIALNUMBER NOT NULL 
- `Status` VDT_STRING10 NOT NULL 

---

### DWH.stgDimPatientPrimaryOncologistRefPhysician
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `PrimaryOncologistSer` VDT_SERIALNUMBER NOT NULL 
- `PrimaryReferringPhycianSer` VDT_SERIALNUMBER NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DimPrimaryOncologistID` VDT_SERIALNUMBER NOT NULL 
- `DimPrimaryReferringPhysicianID` VDT_SERIALNUMBER NOT NULL 
- `RowNumber` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimPatientUpdSmokingDates
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `PatientId` nvarchar NOT NULL 
- `PatientId2` nvarchar NOT NULL 
- `ctrPatientSer` VDT_SERIALNUMBER NOT NULL 
- `SmokingSinceDate` VDT_DATETIME NOT NULL 
- `SmokingQuitDate` VDT_DATETIME NOT NULL 
- `AlcoholQuitDate` VDT_DATETIME NOT NULL 
- `NoYearsQuitAlcohol` VDT_INT NOT NULL 
- `NoYearsQuitSmoking` VDT_INT NOT NULL 
- `NoYearsActiveSmoker` VDT_INT NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimPayor
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PayorSer` VDT_SERIALNUMBER NOT NULL 
- `PayorAuthorizationSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimPayorAuthDel
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PayorSer` VDT_SERIALNUMBER NOT NULL 
- `PayorAuthorizationSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimPayorDel
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `PayorSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimPlanCreationUserNameStatusDate
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ctrPlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `TreatmentType` VDT_TREATMENTTYPE NOT NULL 

---

### DWH.stgDimPrescription_PredecessorData
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrPrescriptionSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPredecessorPrescriptionSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgDimResource
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `DimLookupID_ResourceType` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrstkh_id` VDT_STRING20 NOT NULL 

---

### DWH.stgDimStatusIconImageFile
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrstatus_icon_id` VDT_INT NOT NULL 
- `ImageFile` varbinary NOT NULL 

---

### DWH.stgDimStructure
**Columns:** 39 | **Foreign Keys:** 0

**Columns:**
- `DimStructureID` VDT_SERIALNUMBER NOT NULL [PK]
- `StructureSer` VDT_SERIALNUMBER NOT NULL 
- `StructureSetSer` VDT_SERIALNUMBER NOT NULL 
- `StructureId` VDT_ID_LONG NOT NULL 
- `StructureName` VDT_NAME NOT NULL 
- `StructureTypeSer` VDT_SERIALNUMBER NOT NULL 
- `DicomType` VDT_ID NOT NULL 
- `SubType` VDT_ID NOT NULL 
- `Comment` VDT_COMMENT NOT NULL 
- `ROINumber` VDT_INT NOT NULL 
- `ROIObservationNumber` VDT_INT NOT NULL 
- `GenerationAlgorithm` VDT_STRING16 NOT NULL 
- `GenAlgoComment` VDT_STRING64 NOT NULL 
- `DVHLineColor` VDT_INT NOT NULL 
- `DVHLineStyle` VDT_INT NOT NULL 
- `DVHLineWidth` VDT_FLOAT NOT NULL 
- `FirstSlice` VDT_INT NOT NULL 
- `LastSlice` VDT_INT NOT NULL 
- `MaterialCTValue` VDT_FLOAT NOT NULL 
- `MaterialSer` VDT_SERIALNUMBER NOT NULL 
- `ROIPhysicalProperty` VDT_STRING254 NOT NULL 
- `ROIPhysicalPropertyValue` VDT_STRING254 NOT NULL 
- `SearchCTHigh` VDT_FLOAT NOT NULL 
- `SearchCTLow` VDT_FLOAT NOT NULL 
- `EUDAlpha` VDT_FLOAT NOT NULL 
- `TCPAlpha` VDT_FLOAT NOT NULL 
- `TCPBeta` VDT_FLOAT NOT NULL 
- `TCPGamma` VDT_FLOAT NOT NULL 
- `ThicknessCm` VDT_FLOAT NOT NULL 
- `FileName` VDT_FILENAME NOT NULL 
- `ROIObservationId` VDT_ID NOT NULL 
- `ROIMaterialId` VDT_ID NOT NULL 
- `VolumeCodeDesignator` VDT_ID NOT NULL 
- `VolumeCodeVersion` VDT_ID NOT NULL 
- `VolumeCodeValue` VDT_STRING16 NOT NULL 
- `VolumeCodeMeaning` VDT_STRING64 NOT NULL 
- `Status` VDT_STRING64 NOT NULL 
- `StatusDate` VDT_DATETIME NOT NULL 
- `IsVisible` VDT_FLAG_TRUE_DEFAULT NOT NULL 

---

### DWH.stgDimUserUpdateProfType
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `ProfType` VDT_INT NOT NULL 
- `ProfDescription` VDT_STRING40 NOT NULL 

---

### DWH.stgDoseContributionModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgFactActivityBilling
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `CompletedBy` VDT_SERIALNUMBER NOT NULL 
- `ctrActInstProcCodeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactActivityBillingUpdSer
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendingOncologistSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActInstProcCodeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCategorySer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactActivityBilling_DimHospitalDeptID
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityCaptureSer` VDT_SERIALNUMBER NOT NULL 
- `ctrActInstProcCodeSer` VDT_SERIALNUMBER NOT NULL 
- `DimHospitalDepartmentID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactActivityBilling_MO
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `bill_event_id` VDT_INT NOT NULL 
- `pt_id` nchar NOT NULL 
- `pt_visit_id` int NOT NULL 

---

### DWH.stgFactActivityBilling_RO
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `ActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactActivityDiagnosis
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `ActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityCaptureSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityCaptureRevCount` VDT_REVISIONCOUNT NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactActivityDiagnosisErrorData
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `ActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityCaptureSer` VDT_SERIALNUMBER NOT NULL 
- `ActivityCaptureRevCount` VDT_REVISIONCOUNT NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactBrachySourcePosition
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `ctrSourcePositionSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactCourseDiagnosis
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `ChangeFlag` nvarchar NOT NULL 

---

### DWH.stgFactCourseDiagnosisErrorData
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `CourseSer` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactInVivoDosimetry
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `InVivoDosimetrySer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactPatientAllergy
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `allergy_id` int NOT NULL 

---

### DWH.stgFactPatientCurrentMedication
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `ctragt_name` VDT_STRING50 NOT NULL 
- `ctrdosage_form` VDT_INT NOT NULL 
- `ctrdate_started` VDT_DATETIME NOT NULL 

---

### DWH.stgFactPatientDeathCause_MO
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `DimLookupID_PatientDeathCause` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactPatientDiagnosis
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `diagnosis_ser` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `dx_id` VDT_INT NOT NULL 
- `pt_id` VDT_STRING20 NOT NULL 

---

### DWH.stgFactPatientDiagnosisCellCategory
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `RowNumber` VDT_BIGNUMBER NOT NULL 
- `CellCategory` VDT_BIGNUMBER NOT NULL 
- `ctrDiagnosisID` VDT_BIGNUMBER NOT NULL 
- `ctrDiagnosisSer` VDT_BIGNUMBER NOT NULL 
- `ctrPatientSer` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING64 NOT NULL 

---

### DWH.stgFactPatientDiagnosisType
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrDiagnosisID` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `DiagnosisType` nvarchar NOT NULL 

---

### DWH.stgFactPatientDiagnosis_DimDxSite
**Columns:** 10 | **Foreign Keys:** 0

**Columns:**
- `Id` VDT_BIGNUMBER NOT NULL 
- `BodySystem` VDT_SERIALNUMBER NOT NULL 
- `DxSite` VDT_SERIALNUMBER NOT NULL 
- `CellCategory` VDT_SERIALNUMBER NOT NULL 
- `DxSiteDateTime` VDT_DATETIME NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `ctrDiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientSer` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING64 NOT NULL 
- `pt_stage_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientDiagnosis_OnSetDateCode
**Columns:** 10 | **Foreign Keys:** 0

**Columns:**
- `Id` VDT_BIGNUMBER NOT NULL 
- `OnSetDateCode` VDT_INT NOT NULL 
- `TStage` VDT_STRING32 NOT NULL 
- `NStage` VDT_STRING32 NOT NULL 
- `MStage` VDT_STRING32 NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `ctrDiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientSer` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING64 NOT NULL 
- `pt_stage_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientDiagnosis_StageScheme
**Columns:** 7 | **Foreign Keys:** 0

**Columns:**
- `Id` VDT_BIGNUMBER NOT NULL 
- `DimLookupID_StageScheme` VDT_SERIALNUMBER NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `ctrDiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientSer` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING64 NOT NULL 
- `ctrpt_stage_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientDiagnosis_StagingCorrection
**Columns:** 9 | **Foreign Keys:** 0

**Columns:**
- `Id` VDT_BIGNUMBER NOT NULL 
- `TStage` VDT_STRING32 NOT NULL 
- `NStage` VDT_STRING32 NOT NULL 
- `MStage` VDT_STRING32 NOT NULL 
- `ctrDiagnosisID` VDT_INT NOT NULL 
- `ctrDiagnosisSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPatientSer` VDT_BIGNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING64 NOT NULL 
- `pt_stage_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientEncounter
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` nchar NOT NULL 
- `ctrpt_agenda_hdr_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientFamilyHistory
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `fam_hx_id` int NOT NULL 

---

### DWH.stgFactPatientImageDel
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `ImageSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactPatientLabResult
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `pt_visit_id` VDT_INT NOT NULL 
- `test_id` VDT_INT NOT NULL 
- `test_result_group_id` VDT_INT NOT NULL 
- `test_result_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientMedicalHistory
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 

---

### DWH.stgFactPatientMedoncTreatUpd
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `pt_tx_id` VDT_INT NOT NULL 
- `ctrpt_dx_id` VDT_INT NOT NULL 
- `PtTreatmentIntent` VDT_INT NOT NULL 
- `PtTreatmentUse` VDT_INT NOT NULL 
- `PtTreatmentPlanInitDate` VDT_DATETIME NOT NULL 

---

### DWH.stgFactPatientPayor
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `PatientPayorSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactPatientPayorAccountNumber
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `AccountBillingCodeId` VDT_STRING128 NOT NULL 

---

### DWH.stgFactPatientSocialHistory
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `pt_soc_hx_id` int NOT NULL 

---

### DWH.stgFactPatientStatusIcon
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` nchar NOT NULL 
- `ctrpt_status_icon_id` VDT_INT NOT NULL 

---

### DWH.stgFactPatientToxicity
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `pt_visit_id` int NOT NULL 
- `pt_tr_asmt_id` int NOT NULL 

---

### DWH.stgFactPhysicianOrder
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactQuestionnaires
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `pt_visit_id` int NOT NULL 
- `qstr_name` nchar NOT NULL 
- `qstr_id` int NOT NULL 
- `question_id` int NOT NULL 

---

### DWH.stgFactRxAdminAgtLevel
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `pt_id` VDT_STRING20 NOT NULL 
- `pt_visit_id` VDT_INT NOT NULL 
- `rx_id` VDT_INT NOT NULL 
- `item_no` VDT_INT NOT NULL 
- `agt_level_id` VDT_INT NOT NULL 

---

### DWH.stgFactRxAdminDetail
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `pt_id` VDT_STRING20 NOT NULL 
- `admn_id` VDT_INT NOT NULL 
- `admn_detail_id` VDT_INT NOT NULL 

---

### DWH.stgFactRxDispensary
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `pt_visit_id` VDT_INT NOT NULL 
- `rx_id` VDT_INT NOT NULL 
- `item_no` VDT_INT NOT NULL 
- `disp_id` VDT_INT NOT NULL 

---

### DWH.stgFactTreatmentHistoryNominalEnergy
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `Id` int NOT NULL 
- `ctrRadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `DimTreatmentTransactionID` VDT_SERIALNUMBER NOT NULL 
- `NominalEnergy` VDT_ENERGY NOT NULL 

---

### DWH.stgFactTreatmentHistory_AuthorizedBy
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `RefPointLogSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactTreatmentHistory_SignOffUserNames
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `RadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `DimTreatmentTransactionID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactTreatmentHistory_TreatmentDeliveryType
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `RadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `TreatmentDeliveryType` VDT_STRING16 NOT NULL 
- `DimTreatmentTransactionID` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgFactTreatmentHistory_UpdateAllRules
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `RadiationHstrySer` VDT_SERIALNUMBER NOT NULL 
- `DimTreatmentTransactionID` VDT_SERIALNUMBER NOT NULL 
- `TreatmentDeliveryType` VDT_STRING16 NOT NULL 

---

### DWH.stgFactVisitNote
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `pt_id` nchar NOT NULL 
- `pt_visit_id` int NOT NULL 
- `visit_note_id` int NOT NULL 

---

### DWH.stgFieldModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgImageCourseIdCorrection
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_INT NOT NULL 
- `ImageSer` VDT_SERIALNUMBER NOT NULL 
- `StudySer` VDT_SERIALNUMBER NOT NULL 
- `SeriesSer` VDT_SERIALNUMBER NOT NULL 
- `CourseSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgImageModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgMOPatientEmergencyWorkphoneRelationship
**Columns:** 21 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `BirthPlace` VDT_STRING60 NOT NULL 
- `DoNotHospitalize` VDT_STRING1 NOT NULL 
- `DoNotResuscitate` VDT_STRING1 NOT NULL 
- `Ethnicity` VDT_STRING64 NOT NULL 
- `FatherName` VDT_STRING32 NOT NULL 
- `FeedingRestrictions` VDT_STRING1 NOT NULL 
- `HasLivingWill` VDT_STRING1 NOT NULL 
- `HealthCaredpoa` VDT_STRING1 NOT NULL 
- `IsAutopsyRequested` VDT_STRING1 NOT NULL 
- `IsOrganDonor` VDT_STRING1 NOT NULL 
- `MedicationRestrictions` VDT_STRING1 NOT NULL 
- `MotherMaidenName` VDT_STRING32 NOT NULL 
- `MotherName` VDT_STRING32 NOT NULL 
- `PatientEmergencyContactRelationship` VDT_STRING64 NOT NULL 
- `PatientEmergencyContactWorkPhone` VDT_PHONENUMBER NOT NULL 
- `PatientMaritalStatus` VDT_STRING10 NOT NULL 
- `PatientOccupation` VDT_STRING32 NOT NULL 
- `PatientPresentEmployerName` VDT_STRING32 NOT NULL 
- `Religion` VDT_STRING64 NOT NULL 
- `TreatmentRestrictions` VDT_STRING1 NOT NULL 

---

### DWH.stgOverrideModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgPatientDoctorKeys
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ResourceSer` VDT_SERIALNUMBER NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgPlanModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgReconciliation_TempTableMetaData
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_BIGNUMBER NOT NULL [PK]
- `TableName` sysname NOT NULL 
- `IsActive` bit NOT NULL 
- `TableMetaDataID` VDT_BIGNUMBER NOT NULL 

---

### DWH.stgReconciliation_TempTableMetaData_EXEC_History
**Columns:** 14 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_BIGNUMBER NOT NULL 
- `TableMetaDataID` VDT_BIGNUMBER NOT NULL 
- `ReconcilationType` nvarchar NOT NULL 
- `DWPreExecSQLCommand` nvarchar NOT NULL 
- `DWPostExecSQLCommand` nvarchar NOT NULL 
- `DWUpdateQuery` nvarchar NOT NULL 
- `DWInsertQuery` nvarchar NOT NULL 
- `DWDeleteQuery` nvarchar NOT NULL 
- `DWStatus` VDT_INT NOT NULL 
- `SkipAfterNoofTry` VDT_INT NOT NULL 
- `SkipCount` VDT_INT NOT NULL 
- `DWExecStartDate` VDT_DATETIME NOT NULL 
- `DWExecEndDate` VDT_DATETIME NOT NULL 
- `LogID` VDT_BIGNUMBER NOT NULL 

---

### DWH.stgRefPointModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgTempUpgradePlanStatusUser
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `PlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `PlanRevision` VDT_INT NOT NULL 
- `RTPlanSer` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stgTreatmentHistoryModel
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `Status` tinyint NOT NULL 

---

### DWH.stgUniquePatientAdmissionStatus
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `RowID` int NOT NULL 
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `IsProcessComplete` bit NOT NULL 

---

### DWH.stgUpdDimPlanRTTreatment
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ctrPlanSetupSer` VDT_SERIALNUMBER NOT NULL 
- `RTTreatmentTechnique` VDT_STRING256 NOT NULL 

---

### DWH.stgUpdateSessionData
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `Id` int NOT NULL 
- `DimCourseID` VDT_SERIALNUMBER NOT NULL 
- `NoTxSessionRemaining` VDT_INT NOT NULL 
- `NoTxSessionPlanned` VDT_INT NOT NULL 
- `NoTxSessionDelivered` VDT_INT NOT NULL 

---

### DWH.stgUpgradeDimActivityTransaction_MO
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `pt_id` VDT_STRING20 NOT NULL 
- `pt_visit_id` VDT_INT NOT NULL 
- `IsVisitTypeOpenChart` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `DxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 

---

### DWH.stgUpgradeDimActivityTransaction_RO
**Columns:** 13 | **Foreign Keys:** 0

**Columns:**
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `AppointmentInstanceFlag` VDT_FLAG_TRUE_DEFAULT NOT NULL 
- `ActivityStartDateTime` VDT_DATETIME NOT NULL 
- `ActivityEndDateTime` VDT_DATETIME NOT NULL 
- `ScheduledEndTime` VDT_DATETIME NOT NULL 
- `AppointmentDateTime` VDT_DATETIME NOT NULL 
- `DerivedAppointmentTaskDate` VDT_DATETIME NOT NULL 
- `AppointmentStatus` VDT_STRING64 NOT NULL 
- `AppointmentResourceStatus` VDT_STRING64 NOT NULL 
- `ActivityOwnerFlag` VDT_FLAG_FALSE_DEFAULT NOT NULL 
- `DxSite_DerivedAppointmentTaskDate` VDT_STRING254 NOT NULL 

---

### DWH.stgUpgradeDimPayorAuthDel
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `PayorSer` VDT_SERIALNUMBER NOT NULL 
- `PayorAuthorizationSer` VDT_SERIALNUMBER NOT NULL 
- `AuthorizedBy` VDT_NAME NOT NULL 
- `AuthorizationPhone` VDT_PHONENUMBER NOT NULL 

---

### DWH.stgUpgradeDimRxAgtGeneralOrders
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` nchar NOT NULL [PK]
- `ctrpt_visit_id` int NOT NULL [PK]
- `ctrrx_id` int NOT NULL [PK]
- `ctrRxAgtItemNo` int NOT NULL [PK]
- `GeneralOrders` nvarchar NOT NULL 
- `Rno` VDT_BIGNUMBER NOT NULL 

---

### DWH.stgUpgradeDimRxDateTimes
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `ctrpt_id` nchar NOT NULL [PK]
- `ctrpt_visit_id` int NOT NULL [PK]
- `ctrrx_id` int NOT NULL [PK]
- `appr_tstamp` datetime NOT NULL 
- `date_time_sent` datetime NOT NULL 
- `Rno` VDT_BIGNUMBER NOT NULL 

---

### DWH.stgUpgradeDimTreatmentTransaction
**Columns:** 5 | **Foreign Keys:** 0

**Columns:**
- `ctrRadiationHstrySer` VDT_SERIALNUMBER NOT NULL [PK]
- `Rno` VDT_SERIALNUMBER NOT NULL 
- `CouchLatIso` VDT_COUCHPARAM NOT NULL 
- `CouchLngIso` VDT_COUCHPARAM NOT NULL 
- `CouchVrtIso` VDT_COUCHPARAM NOT NULL 

---

### DWH.stgUpgradeDimVisitEventDetail
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrinst_id` VDT_STRING30 NOT NULL 
- `ctrunavl_hdr_id` VDT_INT NOT NULL 
- `EventTypeEventName` VDT_STRING40 NOT NULL 
- `EventTypeSchEventName` VDT_STRING40 NOT NULL 

---

### DWH.stgUpgradeFactPatient
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `PatientSer` VDT_SERIALNUMBER NOT NULL 
- `ctrPrimaryOncologistSer` VDT_STRING10 NOT NULL 

---

### DWH.stgUpgradeFactPatientDiagnosis
**Columns:** 4 | **Foreign Keys:** 0

**Columns:**
- `ctrDiagnosisID` VDT_SERIALNUMBER NOT NULL 
- `ctrpt_id` VDT_STRING20 NOT NULL 
- `DimPatientID` VDT_SERIALNUMBER NOT NULL 
- `Ranking` nchar NOT NULL 

---

### DWH.stg_AppointmentDataFromDW_DimActivityTransaction
**Columns:** 11 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL [PK]
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `DimActivityTransactionID` VDT_SERIALNUMBER NOT NULL 
- `DimResourceGroupID` VDT_SERIALNUMBER NOT NULL 
- `RowNumber` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceGroupSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 
- `AppointmentResourceStatus` VDT_STRING64 NOT NULL 
- `DimLookupID_AppointmentResourceStatus` VDT_SERIALNUMBER NOT NULL 

---

### DWH.stg_ResourceGroupDataFromAria_DimActivityTransaction
**Columns:** 8 | **Foreign Keys:** 0

**Columns:**
- `ID` VDT_SERIALNUMBER NOT NULL [PK]
- `ctrActivityInstanceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrScheduledActivitySer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceSer` VDT_SERIALNUMBER NOT NULL 
- `ctrAttendeeSer` VDT_SERIALNUMBER NOT NULL 
- `ctrResourceGroupSer` VDT_SERIALNUMBER NOT NULL 
- `AppointmentResourceStatus` VDT_STRING64 NOT NULL 
- `RowNumber` VDT_SERIALNUMBER NOT NULL 

---


## Schema: audit
Tables: 4

### audit.CommandLog
**Columns:** 6 | **Foreign Keys:** 0

**Columns:**
- `LogID` int NOT NULL 
- `CommandID` int NOT NULL 
- `Key` varchar NOT NULL 
- `Type` varchar NOT NULL 
- `Value` varchar NOT NULL 
- `LogTime` datetime NOT NULL 

---

### audit.ExecutionLog
**Columns:** 13 | **Foreign Keys:** 0

**Columns:**
- `LogID` int NOT NULL [PK]
- `ParentLogID` int NOT NULL 
- `Description` varchar NOT NULL 
- `PackageName` varchar NOT NULL 
- `PackageGuid` uniqueidentifier NOT NULL 
- `MachineName` varchar NOT NULL 
- `ExecutionGuid` uniqueidentifier NOT NULL 
- `LogicalDate` datetime NOT NULL 
- `Operator` varchar NOT NULL 
- `StartTime` datetime NOT NULL 
- `EndTime` datetime NOT NULL 
- `Status` tinyint NOT NULL 
- `FailureTask` varchar NOT NULL 

---

### audit.ProcessLog
**Columns:** 3 | **Foreign Keys:** 0

**Columns:**
- `LogID` int NOT NULL 
- `RootTableName` sysname NOT NULL 
- `PartitionDate` datetime NOT NULL 

---

### audit.StatisticLog
**Columns:** 8 | **Foreign Keys:** 0

**Columns:**
- `LogID` int NOT NULL 
- `ComponentName` varchar NOT NULL 
- `Rows` int NOT NULL 
- `TimeMS` int NOT NULL 
- `MinRowsPerSec` int NOT NULL 
- `MeanRowsPerSec` int NOT NULL 
- `MaxRowsPerSec` int NOT NULL 
- `LogTime` datetime NOT NULL 

---


## Schema: dbo
Tables: 3

### dbo.ConfigTablesToDropFKAndIgnoreTableForCleanup
**Columns:** 2 | **Foreign Keys:** 0

**Columns:**
- `ID` int NOT NULL [PK]
- `TableName` sysname NOT NULL 

---

### dbo.__RefactorLog
**Columns:** 1 | **Foreign Keys:** 0

**Columns:**
- `OperationKey` uniqueidentifier NOT NULL [PK]

---

### dbo.sysssislog
**Columns:** 12 | **Foreign Keys:** 0

**Columns:**
- `id` int NOT NULL [PK]
- `event` sysname NOT NULL 
- `computer` nvarchar NOT NULL 
- `operator` nvarchar NOT NULL 
- `source` nvarchar NOT NULL 
- `sourceid` uniqueidentifier NOT NULL 
- `executionid` uniqueidentifier NOT NULL 
- `starttime` datetime NOT NULL 
- `endtime` datetime NOT NULL 
- `datacode` int NOT NULL 
- `databytes` image NOT NULL 
- `message` nvarchar NOT NULL 

---

