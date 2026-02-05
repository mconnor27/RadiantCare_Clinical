# Database Schema Summary - Key Tables

This is a condensed reference of the most important tables for common queries.

## Core Activity Tables

### `DWH.DimActivityTransaction`
**Key Columns:** `DimActivityTransactionID`, `DimActivityID`, `DimResourceID`, `DimResourceGroupID`, `DimLookupID_AppointmentStatus`, `DimLookupID_ActualResourceType`, `DimUserID_ActivityCreatedBy`, `DimUserID_ActivityCompletedBy`, `DimDateID_ScheduledEndTime`, `DimDateID_AppointmentDateTime` (+24 more)

**Foreign Keys:** 17 relationships
- `DimActivityID` → `DWH.DimActivity`
- `DimResourceID` → `DWH.DimResource`
- `DimResourceGroupID` → `DWH.DimResourceGroup`
- `DimLookupID_AppointmentStatus` → `DWH.DimLookup`
- `DimLookupID_ActualResourceType` → `DWH.DimLookup`
- ... and 12 more

**Total Columns:** 58

### `DWH.DimActivity`
**Key Columns:** `DimActivityID`, `ctrActivitySer`, `ctrActivityCategorySer`, `LogID`, `DimLookupID_ActivityObjectStatus`

**Total Columns:** 31

### `DWH.DimActivityAttribute`
**Key Columns:** `DimActivityAttributeID`, `DimActivityID`, `ctrUserDefActAttrSer`, `ctrActivityAttributeSer`, `LogID`

**Foreign Keys:** 1 relationships
- `DimActivityID` → `DWH.DimActivity`

**Total Columns:** 10

### `DWH.FactActivityBilling`
**Key Columns:** `FactActivityBillingID`, `DimProcedureCodeID`, `DimActivityID`, `DimLookupID_ActivityCategory`, `DimResourceID_Activity`, `DimActivityTransactionID`, `DimPatientID`, `DimCourseID`, `DimHospitalDepartmentID`, `DimDoctorID` (+40 more)

**Foreign Keys:** 31 relationships
- `DimProcedureCodeID` → `DWH.DimProcedureCode`
- `DimActivityID` → `DWH.DimActivity`
- `DimLookupID_ActivityCategory` → `DWH.DimLookup`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction`
- `DimPatientID` → `DWH.DimPatient`
- ... and 26 more

**Total Columns:** 105

## People & Resources

### `DWH.DimPatient`
**Key Columns:** `DimPatientID`, `ctrPatientSocialHistoryId`, `ctrPatientSer`, `ctrpt_id`, `ctrHospitalSer`, `ctrPrimaryOncologistSer`, `ctrPrimaryReferringPhysicianSer`, `LogID`

**Total Columns:** 79

### `DWH.DimDoctor`
**Key Columns:** `DimDoctorID`, `DimLocationID`, `DimLookupID_ResourceType`, `ctrResourceSer`, `LogID`, `ctrstkh_id`

**Foreign Keys:** 2 relationships
- `DimLocationID` → `DWH.DimLocation`
- `DimLookupID_ResourceType` → `DWH.DimLookup`

**Total Columns:** 30

### `DWH.DimResource`
**Key Columns:** `DimResourceID`, `DimLookupID_ResourceType`, `ActualResourceID`, `ctrResourceSer`, `LogID`, `ctrstkh_id`

**Foreign Keys:** 1 relationships
- `DimLookupID_ResourceType` → `DWH.DimLookup`

**Total Columns:** 6

### `DWH.DimUser`
**Key Columns:** `DimUserID`, `DimResourceID`, `DimResourceID_StakeHolder`, `UserCUID`, `ctrAppUserSer`, `LogID`, `ctrinst_id`

**Foreign Keys:** 2 relationships
- `DimResourceID` → `DWH.DimResource`
- `DimResourceID_StakeHolder` → `DWH.DimResource`

**Total Columns:** 13

### `DWH.DimResourceGroup`
**Key Columns:** `DimResourceGroupID`, `DimHospitalDepartmentID`, `DimLookupID_ResourceGroupCode`, `DimLookupID_GroupType`, `DimLookupID_ObjectStatus`, `ctrResourceGroupSer`, `ctrDepartmentSer`, `LogID`

**Foreign Keys:** 3 relationships
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment`
- `DimLookupID_ResourceGroupCode` → `DWH.DimLookup`
- `DimLookupID_ObjectStatus` → `DWH.DimLookup`

**Total Columns:** 15

## Organization & Location

### `DWH.DimHospitalDepartment`
**Key Columns:** `DimHospitalDepartmentID`, `ctrHospitalSer`, `ctrDepartmentSer`, `LogID`, `ctrinst_id`

**Total Columns:** 15

### `DWH.DimInstituteLocation`
**Key Columns:** `DimInstituteLocationID`, `DimHospitalDepartmentID`, `ctrloc_id`, `ctrbldg_id`, `ctrfloor_id`, `ctrroom_id`, `LogID`

**Foreign Keys:** 1 relationships
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment`

**Total Columns:** 22

## Time & Calendar

### `DWH.DimDate`
**Key Columns:** `DimDateID`

**Total Columns:** 40

## Clinical Data

### `DWH.DimCourse`
**Key Columns:** `DimCourseID`, `DimPatientID`, `ctrCourseSer`, `DimLookupID_ClinicalStatus`, `DimLookupID_TreatmentIntentType`, `DimDxSiteID`, `LogID`

**Foreign Keys:** 2 relationships
- `DimPatientID` → `DWH.DimPatient`
- `DimDxSiteID` → `DWH.DimDxSite`

**Total Columns:** 15

### `DWH.DimDiagnosisCode`
**Key Columns:** `DimDiagnosisCodeID`, `LogID`

**Total Columns:** 31

### `DWH.FactPatientDiagnosis`
**Key Columns:** `FactPatientDiagnosisID`, `DimPatientID`, `DimDiagnosisCodeID`, `DimICDOSiteID`, `DimCellTypeID`, `DimLookupID_DiagnosisStatus`, `DimLookupID_Ranking`, `DimLookupID_Source`, `DimLookupID_HistoricDxFlag`, `DimLookupID_CellCategory` (+27 more)

**Foreign Keys:** 29 relationships
- `DimPatientID` → `DWH.DimPatient`
- `DimDiagnosisCodeID` → `DWH.DimDiagnosisCode`
- `DimICDOSiteID` → `DWH.DimICDOSite`
- `DimCellTypeID` → `DWH.DimCellType`
- `DimLookupID_DiagnosisStatus` → `DWH.DimLookup`
- ... and 24 more

**Total Columns:** 83

## Billing & Charges

### `DWH.DimProcedureCode`
**Key Columns:** `DimProcedureCodeID`, `ctrProcedureCodeSer`, `LogID`, `DimDateID_ChangeDate`, `DimLookupID_ProcCodeObjectStatus`

**Total Columns:** 21

### `DWH.DimPayor`
**Key Columns:** `DimPayorID`, `ctrPayorSer`, `ctrPlanTypeSer`, `ctrPayorAuthorizationSer`, `LogID`, `DimHospitalDepartmentID`, `ctrins_co_id`, `ctrins_co_parent_id`

**Foreign Keys:** 1 relationships
- `DimHospitalDepartmentID` → `DWH.DimHospitalDepartment`

**Total Columns:** 21

### `DWH.FactActivityBilling`
**Key Columns:** `FactActivityBillingID`, `DimProcedureCodeID`, `DimActivityID`, `DimLookupID_ActivityCategory`, `DimResourceID_Activity`, `DimActivityTransactionID`, `DimPatientID`, `DimCourseID`, `DimHospitalDepartmentID`, `DimDoctorID` (+40 more)

**Foreign Keys:** 31 relationships
- `DimProcedureCodeID` → `DWH.DimProcedureCode`
- `DimActivityID` → `DWH.DimActivity`
- `DimLookupID_ActivityCategory` → `DWH.DimLookup`
- `DimActivityTransactionID` → `DWH.DimActivityTransaction`
- `DimPatientID` → `DWH.DimPatient`
- ... and 26 more

**Total Columns:** 105

## Reference Data

### `DWH.DimLookup`
**Key Columns:** `DimLookupID`, `ctrLookupTableSer`, `LogID`

**Total Columns:** 16


## Important Implicit Relationships (via ctr***Ser)

These connections exist through matching column names, not formal foreign keys:

- **Patient → Primary Oncologist:** `DimPatient.ctrPrimaryOncologistSer` = `DimDoctor.ctrResourceSer`
- **Patient → Referring Physician:** `DimPatient.ctrPrimaryReferringPhysicianSer` = `DimDoctor.ctrResourceSer`
- **Resource → Doctor:** `DimResource.ctrResourceSer` = `DimDoctor.ctrResourceSer`
- **User → Resource:** `DimUser.DimResourceID` = `DimResource.DimResourceID`
- **ActivityTransaction → Billing:** `DimActivityTransaction.DimActivityTransactionID` = `FactActivityBilling.DimActivityTransactionID`
