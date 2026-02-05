# Quick Reference: Common Query Patterns

## Activities/Appointments

### Basic Activity List
```sql
SELECT 
    act.ActivityCode,
    act.ActivityNameENU,
    dateStart.FullDate AS StartDate,
    dept.DepartmentName
FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimActivity act ON at.DimActivityID = act.DimActivityID
LEFT JOIN DWH.DimDate dateStart ON at.DimDateID_ActivityStartDateTime = dateStart.DimDateID
LEFT JOIN DWH.DimHospitalDepartment dept ON at.DimHospitalDepartmentID = dept.DimHospitalDepartmentID
WHERE dateStart.Year = 2025
```

### Activities with All Three Doctors
```sql
SELECT 
    -- Activity
    act.ActivityCode,
    
    -- Dates
    dateCreated.FullDate AS CreatedDate,
    dateEnd.FullDate AS CompletedDate,
    
    -- Doctor 1: Scheduled
    scheduledDoc.DoctorFullName AS ScheduledDoctor,
    
    -- Doctor 2: Completed By
    completedDoc.DoctorFullName AS CompletedByDoctor,
    
    -- Doctor 3: Patient's Primary Oncologist
    primaryOnc.DoctorFullName AS PrimaryOncologist,
    
    -- Patient
    pat.LastName + ', ' + pat.FirstName AS PatientName

FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimActivity act ON at.DimActivityID = act.DimActivityID
LEFT JOIN DWH.DimDate dateCreated ON at.DimDateID_CreationDate = dateCreated.DimDateID
LEFT JOIN DWH.DimDate dateEnd ON at.DimDateID_ActivityEndDateTime = dateEnd.DimDateID

-- Scheduled doctor (via Resource)
LEFT JOIN DWH.DimResource res ON at.DimResourceID = res.DimResourceID
LEFT JOIN DWH.DimDoctor scheduledDoc ON res.ctrResourceSer = scheduledDoc.ctrResourceSer

-- Completed by doctor (via User → Resource → Doctor)
LEFT JOIN DWH.DimUser usr ON at.DimUserID_ActivityCompletedBy = usr.DimUserID
LEFT JOIN DWH.DimResource completedRes ON usr.DimResourceID = completedRes.DimResourceID
LEFT JOIN DWH.DimDoctor completedDoc ON completedRes.ctrResourceSer = completedDoc.ctrResourceSer

-- Patient and their primary oncologist
LEFT JOIN DWH.DimPatient pat ON at.DimPatientID = pat.DimPatientID
LEFT JOIN DWH.DimDoctor primaryOnc ON pat.ctrPrimaryOncologistSer = primaryOnc.ctrResourceSer
```

### No-Show Analysis
```sql
SELECT 
    dept.DepartmentName,
    COUNT(*) AS TotalAppointments,
    SUM(CASE WHEN at.NoShowFlag = 1 THEN 1 ELSE 0 END) AS NoShows,
    CAST(SUM(CASE WHEN at.NoShowFlag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS DECIMAL(5,2)) AS NoShowRate
FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimHospitalDepartment dept ON at.DimHospitalDepartmentID = dept.DimHospitalDepartmentID
LEFT JOIN DWH.DimDate d ON at.DimDateID_AppointmentDateTime = d.DimDateID
WHERE d.Year = 2025 AND d.Month = 1
GROUP BY dept.DepartmentName
ORDER BY NoShowRate DESC
```

## Patients

### Patient List with Primary Oncologist
```sql
SELECT 
    pat.PatientId,
    pat.LastName + ', ' + pat.FirstName AS PatientName,
    pat.DateOfBirth,
    pat.MedicalRecordNumber,
    doc.DoctorFullName AS PrimaryOncologist,
    doc.DoctorSpecialty
FROM DWH.DimPatient pat
LEFT JOIN DWH.DimDoctor doc ON pat.ctrPrimaryOncologistSer = doc.ctrResourceSer
WHERE pat.PatientObjectStatus = 'Active'
```

### Patient Activity History
```sql
SELECT 
    pat.LastName + ', ' + pat.FirstName AS PatientName,
    act.ActivityNameENU AS Activity,
    d.FullDate AS ActivityDate,
    doc.DoctorFullName AS Doctor,
    status.LookupValue AS Status
FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimPatient pat ON at.DimPatientID = pat.DimPatientID
LEFT JOIN DWH.DimActivity act ON at.DimActivityID = act.DimActivityID
LEFT JOIN DWH.DimDate d ON at.DimDateID_ActivityStartDateTime = d.DimDateID
LEFT JOIN DWH.DimResource res ON at.DimResourceID = res.DimResourceID
LEFT JOIN DWH.DimDoctor doc ON res.ctrResourceSer = doc.ctrResourceSer
LEFT JOIN DWH.DimLookup status ON at.DimLookupID_AppointmentStatus = status.DimLookupID
WHERE pat.PatientId = 'YOUR_PATIENT_ID'
ORDER BY d.FullDate DESC
```

## Doctors/Resources

### Doctor Workload by Month
```sql
SELECT 
    doc.DoctorFullName,
    d.Year,
    d.MonthName,
    COUNT(*) AS AppointmentCount,
    SUM(DATEDIFF(MINUTE, dateStart.FullDate, dateEnd.FullDate)) AS TotalMinutes
FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimResource res ON at.DimResourceID = res.DimResourceID
LEFT JOIN DWH.DimDoctor doc ON res.ctrResourceSer = doc.ctrResourceSer
LEFT JOIN DWH.DimDate d ON at.DimDateID_AppointmentDateTime = d.DimDateID
LEFT JOIN DWH.DimDate dateStart ON at.DimDateID_ActivityStartDateTime = dateStart.DimDateID
LEFT JOIN DWH.DimDate dateEnd ON at.DimDateID_ActivityEndDateTime = dateEnd.DimDateID
WHERE d.Year = 2025
  AND dateEnd.FullDate IS NOT NULL  -- Only completed
GROUP BY doc.DoctorFullName, d.Year, d.MonthName, d.MonthNumber
ORDER BY d.MonthNumber, doc.DoctorFullName
```

### Doctor Specialty Distribution
```sql
SELECT 
    doc.DoctorSpecialty,
    COUNT(DISTINCT doc.DimDoctorID) AS DoctorCount,
    COUNT(DISTINCT pat.DimPatientID) AS PatientCount
FROM DWH.DimDoctor doc
LEFT JOIN DWH.DimPatient pat ON doc.ctrResourceSer = pat.ctrPrimaryOncologistSer
WHERE doc.ResourceObjectStatus = 'Active'
GROUP BY doc.DoctorSpecialty
ORDER BY PatientCount DESC
```

## Departments

### Department Activity Summary
```sql
SELECT 
    dept.DepartmentName,
    COUNT(DISTINCT at.DimActivityTransactionID) AS TotalActivities,
    COUNT(DISTINCT at.DimPatientID) AS UniquePatients,
    COUNT(DISTINCT res.DimResourceID) AS UniqueResources,
    AVG(DATEDIFF(MINUTE, dateStart.FullDate, dateEnd.FullDate)) AS AvgDurationMinutes
FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimHospitalDepartment dept ON at.DimHospitalDepartmentID = dept.DimHospitalDepartmentID
LEFT JOIN DWH.DimResource res ON at.DimResourceID = res.DimResourceID
LEFT JOIN DWH.DimDate dateStart ON at.DimDateID_ActivityStartDateTime = dateStart.DimDateID
LEFT JOIN DWH.DimDate dateEnd ON at.DimDateID_ActivityEndDateTime = dateEnd.DimDateID
LEFT JOIN DWH.DimDate d ON at.DimDateID_CreationDate = d.DimDateID
WHERE d.Year = 2025
  AND dateEnd.FullDate IS NOT NULL
GROUP BY dept.DepartmentName
ORDER BY TotalActivities DESC
```

## Billing

### Activity Billing Summary
```sql
SELECT 
    act.ActivityCode,
    act.ActivityNameENU,
    COUNT(DISTINCT bill.FactActivityBillingID) AS BillingEvents,
    SUM(bill.Quantity) AS TotalQuantity,
    SUM(bill.TotalCharge) AS TotalCharges,
    AVG(bill.TotalCharge) AS AvgCharge
FROM DWH.FactActivityBilling bill
LEFT JOIN DWH.DimActivity act ON bill.DimActivityID = act.DimActivityID
LEFT JOIN DWH.DimDate d ON bill.DimDateID_FromDateOfService = d.DimDateID
WHERE d.Year = 2025
GROUP BY act.ActivityCode, act.ActivityNameENU
ORDER BY TotalCharges DESC
```

## Date Filtering Patterns

### Year/Month/Day
```sql
WHERE d.Year = 2025
  AND d.Month = 1
  AND d.DayOfMonth = 15
```

### Date Range
```sql
WHERE d.FullDate BETWEEN '2025-01-01' AND '2025-12-31'
```

### Last 30 Days
```sql
WHERE d.FullDate >= DATEADD(DAY, -30, GETDATE())
```

### This Month
```sql
WHERE d.Year = YEAR(GETDATE())
  AND d.Month = MONTH(GETDATE())
```

### Business Days Only
```sql
WHERE d.IsWeekday = 1  -- Excludes weekends
```

## Performance Tips

1. **Filter on Date dimension** rather than datetime fields when possible
2. **Use EXISTS** instead of IN for subqueries with large result sets
3. **Index hints** if you know the optimal index: `WITH (INDEX(IndexName))`
4. **NOLOCK hint** for read-only queries on busy tables: `WITH (NOLOCK)`
5. **Limit result sets** in development: `TOP 1000` or `WHERE ... AND RowNum <= 1000`

## Common Filters

### Active Records Only
```sql
WHERE ObjectStatus = 'Active'  -- or 'A' depending on table
```

### Exclude Test/Training Data
```sql
WHERE pat.PatientId NOT LIKE 'TEST%'
  AND pat.PatientId NOT LIKE 'TRAIN%'
```

### Scheduled vs Walk-in
```sql
WHERE at.IsScheduled = 1  -- Scheduled only
-- OR
WHERE at.IsScheduled = 0  -- Walk-ins only
```
