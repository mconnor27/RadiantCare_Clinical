# Claude Agent Instructions

## Data Processing Transparency

Whenever data processing logic is added or adjusted in the application, the agent **must** update the help modal to reflect these changes. This ensures users have complete transparency about how their data is being processed.

### Steps to follow:
1. When adding/modifying data filters, mappings, or transformations in any task module
2. Update the corresponding section in `/Users/Mike/RadiantCare_Clinical/components/header.py`
3. Update the help modal content in the `create_header()` function
4. Ensure the notes are clear, concise, and user-friendly

### Location of Help Modal:
- File: `components/header.py`
- Function: `create_header()`
- Component: `dbc.Modal` with id="help-modal"

### Sections in Help Modal:
- **Tasks (Draw Volumes, Review Plan, Contour Review)**: Data processing for MD-based tasks
- **Simulations**: Location mappings, filtered types, combined types
- **General Notes**: Cross-cutting processing logic (leap years, statistics, projections)
