# Legacy Business Logic Reference

Extracted from the original codebase before rebuild. Reference this when implementing data processing in the new app. Not all of this logic will carry over directly — the new app uses different data sources (AURA_Reports CSVs instead of the old "Department Schedule" exports).

---

## Logic Worth Preserving

### Test Patient Filtering
Exclude test/dummy patients from all clinical data:
```python
test_filter = (
    df['PatientId'].astype(str).str.contains('astro|test', case=False, na=False) |
    df['PatientFullName'].str.lower().str.startswith('zzz', na=False) |
    df['PatientFullName'].str.startswith('Test,', na=False)
)
df = df[~test_filter]
```

### Consult vs Follow-Up Classification
Priority-based decision tree for clinic visits:

| Condition | Result |
|-----------|--------|
| Duration > 60 minutes | **Consult** |
| ActivityName is "Consult" / "Consult - Special request" / "Consult- ADD ON" | **Consult** unless note matches follow-up pattern |
| ActivityName = "Virtual Consult/Follow Up" AND duration < 60 | Check note for follow-up keywords → **Follow-Up**; check for new-patient keywords → **Consult**; default → **Follow-Up** |
| ActivityName = "Virtual Consult/Follow Up" AND duration = 60 | Check note for follow-up indicators → **Follow-Up**; else → **Consult** |
| Any other activity type | **Consult** (fallback) |

Follow-up keyword patterns:
- `follow[\s-]?up|re[\s-]?eval|followup|reeval` (general)
- `\bphone\b|\btelephone\b|f/u` (explicit follow-up for virtual)
- `review|discuss|go\s+over` (context clues for follow-up)
- `working\s+chart|bookmarked` (new patient indicators → consult)

**Note:** The new Clinic Visits.csv already has `ActivityName` values of "Consult", "Follow-Up", and "Virtual Consult/Follow Up" — this classification may be partially handled upstream now. Verify against the new data before reimplementing.

### Department Name Normalization
Some ARIA exports prefix department names with `*`:
```python
df['Department'] = df['Department'].str.replace('*', '', regex=False)
```

### Insurer Categorization
```python
medicare_keywords = ['MEDICARE', 'MEDADVANTAGE', 'MED ADVANTAGE', 'MEDICARE ADVANTAGE']
medicaid_keywords = ['MEDICAID', 'CHPW MEDICAID', 'APPLE HEALTH', 'MOLINA MEDICAID']
# Check Medicare first, then Medicaid, then default to "Private". Null/empty = "Unknown"
```

### CPT Technique Classification
Map billed CPT codes to treatment technique:

| Technique | CPT Codes |
|-----------|----------|
| Conventional | 77402, 77407, 77412, G6003-G6014 |
| SRS | 77372 |
| SBRT | 77373 |
| IMRT | 77385, 77386, G6015, G6016 |
| IGRT | 77014, 77387, 77417, G6002 |

Multi-valued `CPT_Billed` fields: split on comma, strip modifiers (split on `-`), classify each code, combine results.

### Simulation Location Mapping
```python
'CT_RC_LACEY'  → 'Lacey'
'CT_CENTRALIA' → 'Centralia'
'21IX_AB'      → 'Aberdeen'
```
**Note:** The new Simulations.csv already has department/physician info. Check if this mapping is still needed.

### Simulation Type Consolidation
- Filter out: "Bite Block" types
- Combine: "Treatment Device Fabrication" + "initial simulation on PET/CT table" → "PET/CT Sim"

### Leap Year Normalization (for year-over-year charts)
In cumulative day-of-year comparison charts, shift days after Feb 29 in leap years back by 1:
```python
if is_leap:
    year_data.loc[year_data['day_of_year'] > 60, 'day_of_year'] -= 1
```

### LOWESS Smoothing
Slider value (0-10) maps to fraction range (0.01 to 0.50):
```python
frac = 0.01 + (smoothing / 10) * 0.49
smoothed = lowess(y_values, x_numeric, frac=frac, return_sorted=False)
```

### Historical Statistics
- Exclude current/max year from statistics
- Interpolate each year's cumulative data to fill all days
- 95% CI = mean ± 1.96 × std (ddof=1)

### Year-End Projection
```python
projected_final = last_value * (days_in_year / days_elapsed)
```

### Scheduling CSV Footer Handling
ARIA scheduling exports include filter metadata rows at the bottom. Stop reading at the first blank line:
```python
for i, line in enumerate(lines):
    if line.strip() == '':
        data_end = i
        break
```

### Help Modal Content
The existing help modal documents all data processing for user transparency. Key sections:
- Tasks: MD filtering, activity consolidation
- Simulations: location mapping, type filtering/consolidation
- Scheduling: footer removal, department cleanup
- Clinic Visits: test patient removal, consult classification rules
- General: leap year handling, statistics methodology, projections

When rebuilding the help system, carry forward this transparency principle — users should be able to understand how their data is processed.
