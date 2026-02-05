# Varian Database Query Assistant Package

Transform natural language requests into SQL queries instantly using Claude AI with your complete database schema embedded.

## 🎯 What This Does

Instead of manually writing SQL queries, just describe what you need:

**You say:** *"Show me front desk appointments from January with the scheduled doctor, completed by doctor, and patient's primary oncologist"*

**Claude generates:**
```sql
SELECT 
    act.ActivityCode,
    dateCreated.FullDate AS CreationDate,
    scheduledDoc.DoctorFullName AS ScheduledDoctor,
    completedDoc.DoctorFullName AS CompletedByDoctor,
    primaryOnc.DoctorFullName AS PrimaryOncologist,
    dept.DepartmentName
FROM DWH.DimActivityTransaction at
LEFT JOIN DWH.DimActivity act ON at.DimActivityID = act.DimActivityID
-- [rest of query with proper joins]...
```

## 📦 What's Included

### 1. **Setup Guide** 📖
`SETUP_GUIDE.md` - Step-by-step instructions for setting up your Claude Project

### 2. **Schema Files** 🗄️
- **`schema_summary_condensed.md`** (6KB) - Quick reference, optimized for Claude
- **`database_schema.md`** (271KB) - Complete detailed schema
- **`database_schema.json`** (JSON) - Machine-readable format

### 3. **Configuration** ⚙️
- **`claude_project_instructions.md`** - Custom instructions teaching Claude your database
- **`query_patterns_reference.md`** - Common query templates and patterns

### 4. **Interactive Tool** 🎨
- **`database_explorer_integrated_fixed.html`** - Visual database explorer with:
  - Interactive relationship visualization
  - Query builder
  - Table search and filtering
  - Implicit relationship detection (ctr***Ser columns)

## 🚀 Quick Start

### Option A: Claude Project (Recommended)

1. Go to [claude.ai](https://claude.ai) → Projects
2. Create new project: "Varian DB Assistant"
3. Add custom instructions from `claude_project_instructions.md`
4. Upload `schema_summary_condensed.md` to Project Knowledge
5. Start chatting naturally!

**Read:** `SETUP_GUIDE.md` for detailed steps

### Option B: Single Conversation

1. Start new chat with Claude
2. Upload `schema_summary_condensed.md` and `query_patterns_reference.md`
3. Ask: *"Help me write SQL queries using the uploaded schema"*

## 💡 Example Use Cases

### Appointments & Scheduling
```
"No-show rates by department last month"
"Doctor workload for January 2025"
"Front desk appointments scheduled vs completed"
```

### Patient Analytics
```
"Patients grouped by primary oncologist specialty"
"Activity history for patient MRN 12345"
"New patient registrations by month"
```

### Billing & Revenue
```
"Top 10 procedure codes by revenue in Q1"
"Billing events with missing diagnosis codes"
"Average charge per activity type"
```

### Operational Metrics
```
"Average appointment duration by activity type"
"Resources with highest utilization"
"Wait time analysis for treatment rooms"
```

## 🎓 What Makes This Powerful

### Understands Your Database
- Knows all 295 tables and their relationships
- Recognizes implicit joins via `ctr***Ser` columns
- Understands dimensional model (facts and dimensions)

### Generates Quality Queries
- Proper join syntax
- Efficient filtering
- Well-commented code
- Performance-conscious

### Iterative & Conversational
```
You: "Show January appointments"
Claude: [query]
You: "Add patient names"
Claude: [updated query]
You: "Only completed ones"
Claude: [final query]
```

## 📊 Database Overview

**Schemas:** DWH (data warehouse), dbo, audit
**Total Tables:** 295
**Key Tables:**
- `DWH.DimActivityTransaction` - Appointments/activities
- `DWH.DimPatient` - Patient demographics
- `DWH.DimDoctor` - Physician information
- `DWH.DimResource` - Staff/resources
- `DWH.DimDate` - Date dimension
- `DWH.FactActivityBilling` - Billing events

## 🔗 Important Relationships

### Explicit (Foreign Keys)
Standard database relationships with defined foreign keys.

### Implicit (ctr***Ser columns)
Special relationships through matching serial numbers:
- `DimPatient.ctrPrimaryOncologistSer` = `DimDoctor.ctrResourceSer`
- `DimResource.ctrResourceSer` = `DimDoctor.ctrResourceSer`
- `DimUser.DimResourceID` = `DimResource.DimResourceID`

*Your database explorer tool automatically detects these!*

## 📝 Tips for Success

### Be Specific
❌ *"Get some data"*
✅ *"Get patient appointments from January 2025 with doctor names"*

### Iterate Naturally
Start simple, then refine:
1. Basic query
2. Add columns
3. Add filters
4. Add sorting
5. Optimize

### Ask for Explanations
- *"Why did you use that join?"*
- *"Can you explain the implicit relationship?"*
- *"What's a better way to do this?"*

## 🛠️ Files Reference

| File | Size | Purpose | When to Use |
|------|------|---------|-------------|
| `SETUP_GUIDE.md` | 5KB | Setup instructions | First time setup |
| `schema_summary_condensed.md` | 6KB | Quick reference | **Add to Project first** |
| `query_patterns_reference.md` | 7KB | Query templates | Learning common patterns |
| `claude_project_instructions.md` | 6KB | AI instructions | Project custom instructions |
| `database_schema.md` | 271KB | Full schema | Deep dive reference |
| `database_schema.json` | JSON | Machine format | Tool integration |
| `database_explorer_integrated_fixed.html` | HTML | Visual tool | Interactive exploration |

## 🎯 Recommended Workflow

### For Daily Query Writing:
1. **Claude Project** with condensed schema
2. Ask natural questions
3. Copy SQL to your tool (SSMS, Report Builder, etc.)
4. Run and iterate if needed

### For Database Exploration:
1. **Open HTML explorer** in browser
2. Search/filter tables visually
3. See relationships
4. Build queries with Query Builder

### For Learning:
1. **Read query patterns** reference
2. Ask Claude to explain patterns
3. Request variations on queries
4. Build your own library

## 🔄 Keeping Updated

If your database schema changes:
1. Export new schema (using the SQL query from our original conversation)
2. Process through the Python script
3. Update Project Knowledge files
4. Continue chatting!

## 💬 Support & Tips

### Getting Better Results
- Start broad, then narrow
- Reference specific table names if you know them
- Ask for multiple approaches
- Request performance optimization

### Common Requests
- *"Add error handling"*
- *"Make this a stored procedure"*
- *"Convert to SSRS report format"*
- *"Explain the execution plan"*

## 🎉 Next Steps

1. **Read `SETUP_GUIDE.md`** - 5 minute setup
2. **Create Claude Project** - One-time configuration
3. **Upload schema files** - Drag and drop
4. **Start querying!** - Natural language

---

## 📞 Quick Reference

**Main Setup File:** `SETUP_GUIDE.md`
**Best Schema for Claude:** `schema_summary_condensed.md`
**Query Examples:** `query_patterns_reference.md`
**Visual Explorer:** `database_explorer_integrated_fixed.html`

---

**You're ready to 10x your SQL productivity!** 🚀

No more searching through tables, guessing at joins, or spending hours on complex queries. Just describe what you need, and Claude handles the SQL.
