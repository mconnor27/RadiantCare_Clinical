# Setup Guide: Your Personal Database Query Assistant

## 🎯 Goal
Set up a Claude Project that acts as your personal SQL query assistant with full knowledge of your Varian database schema.

---

## ✅ Option 1: Claude Project (RECOMMENDED)

**Best for:** Ongoing work, multiple conversations, persistent context

### Setup Steps:

1. **Go to Claude.ai** and click **"Projects"** in the left sidebar

2. **Create New Project**
   - Name: "Varian Database Assistant" (or your preference)
   - Description: "SQL query assistant for Varian data warehouse"

3. **Add Custom Instructions**
   - Click "Set custom instructions"
   - Copy and paste the contents of `claude_project_instructions.md`

4. **Add Project Knowledge** (add these files):
   - `schema_summary_condensed.md` (6KB - START HERE)
   - `query_patterns_reference.md` (7KB - very useful patterns)
   - Optional: `database_schema.md` (271KB - full detailed schema)
   
   **Note:** Add the condensed summary first. You can always reference the full schema later if needed.

5. **Start Chatting!**
   - Just ask natural language questions about your data
   - Claude will have full context of your schema in every conversation

### Example Queries:

```
"Show me all appointments from the front desk in January with their doctors"

"I need a query for patient primary oncologists grouped by specialty"

"Get activities completed by Dr. Smith in the last month"

"Show me no-show rates by department"
```

---

## ✅ Option 2: Single Conversation with Files

**Best for:** One-off queries, testing, or if you don't have Projects access

### Setup Steps:

1. **Start a new conversation** with Claude

2. **Upload these files** using the attachment button:
   - `schema_summary_condensed.md`
   - `query_patterns_reference.md`

3. **First message template:**
   ```
   I've uploaded my database schema. I need help writing SQL queries for a 
   Varian data warehouse. Please use the schema files to understand my database 
   structure and help me write queries based on natural language requests.
   
   My first query: [YOUR QUERY HERE]
   ```

**Limitation:** You'll need to re-upload files for each new conversation.

---

## ✅ Option 3: Artifacts Approach (Interactive)

**Best for:** Building a reusable query builder interface

I can create an HTML artifact that:
- Embeds your full schema
- Provides an interface to describe what you need
- Uses Claude API to generate queries
- Shows results in a nice interface

Let me know if you want this option!

---

## 📝 Tips for Best Results

### How to Ask Questions:

**Good Examples:**
- "Show me front desk appointments with all three doctors (scheduled, completed by, and primary oncologist)"
- "I need patient activity history grouped by month"
- "Get billing data for radiation treatments in Q1 2025"
- "Find doctors with the highest no-show rates"

**What to Include:**
- Specific columns you want (patient name, dates, doctors, etc.)
- Filters (date ranges, departments, status)
- Grouping or aggregation needs
- Sort order preferences

**Advanced:**
- "Explain the implicit joins you used"
- "Show me an alternative query approach"
- "Optimize this for better performance"
- "Add comments explaining each section"

### Claude Will Automatically:
- ✅ Identify the right tables
- ✅ Handle implicit joins (ctr***Ser columns)
- ✅ Add proper date formatting
- ✅ Include helpful comments
- ✅ Suggest filters and optimizations
- ✅ Explain the query logic

---

## 🎓 Learning Mode

If you want to learn SQL while getting queries:

Add to your Project instructions:
```
When providing queries, also include:
1. A brief explanation of the join strategy
2. Why you chose certain tables
3. Performance considerations
4. Alternative approaches
```

---

## 🔄 Iterative Refinement

You can refine queries naturally:

```
You: "Show me appointments from January"
Claude: [provides query]

You: "Add the patient's primary oncologist"
Claude: [adds the join]

You: "Only show completed ones"
Claude: [adds WHERE clause]

You: "Sort by completion time"
Claude: [adds ORDER BY]
```

---

## 🚀 Advanced Use Cases

### Compare Multiple Approaches
```
"Show me 3 different ways to get doctor workload metrics"
```

### Performance Optimization
```
"This query is slow on 1M rows, can you optimize it?"
```

### Data Validation
```
"Write a query to find orphaned records where the doctor reference is invalid"
```

### Template Building
```
"Create a parameterized query template I can reuse for different date ranges"
```

---

## 📊 Expected Performance

With this setup, you should be able to:
- Get accurate queries in **seconds** (not minutes)
- Iterate on queries **conversationally**
- Learn patterns for **future reference**
- Build a **library of queries** you can reuse

---

## 🆘 Troubleshooting

### "Claude doesn't know my schema"
- Make sure files are added to Project Knowledge
- Check that you're in the correct Project
- Try uploading the condensed schema again

### "Query doesn't work"
- Share the error message with Claude
- Claude will fix it and explain what was wrong

### "I need a different format"
- Just ask! "Can you make this a stored procedure?" or "Export as CSV format"

---

## 📁 Files Included in This Package

1. **`claude_project_instructions.md`** - Custom instructions for Claude
2. **`schema_summary_condensed.md`** - Quick reference (6KB) ⭐ START HERE
3. **`query_patterns_reference.md`** - Common query templates (7KB)
4. **`database_schema.md`** - Full detailed schema (271KB)
5. **`database_schema.json`** - Machine-readable schema (for tools)
6. **`database_explorer_integrated_fixed.html`** - Interactive visual explorer

---

## 🎉 You're Ready!

Go create your Claude Project and start chatting naturally about your database!

Questions? Just ask Claude: "How do I connect to DimPatient?" or "Show me the activity tables" and it'll guide you.
