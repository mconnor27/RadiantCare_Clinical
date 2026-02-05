# Architectural Decisions

## 2025-02-04: Framework — Stay with Dash

**Context:** Evaluated whether to switch frameworks for the rebuild.
**Decision:** Rebuild in Dash (Python), not switch to React or another framework.
**Why:** Python is the team's strength, data layer is pandas-native, Plotly charting is first-class in Dash. Switching would require learning a full JS stack for marginal UI gains.

## 2025-02-04: Navigation — Left sidebar, not top tabs

**Context:** Current app uses top tabs, which became crowded at 6 tabs. New app has 13 pages.
**Decision:** Left sidebar navigation (collapsible: 200px expanded, 60px icon-only).
**Why:** Top tabs don't scale past ~6 items. Left sidebar is the standard for dashboard-density apps (Grafana, Metabase, Looker). Pairs cleanly with the horizontal filter bar — keeps navigation and filtering visually distinct.

## 2025-02-04: Filtering — Mixed approach

**Context:** With multiple charts per page, need to decide whether sidebar filters apply globally or per-chart.
**Decision:** Page-level filters in a horizontal bar at the top of the content area (date range, department, physician) apply to ALL charts. Individual charts can have small inline controls (chart type toggle, smoothing, grouping) in their title bar.
**Why:** Page-level filters reduce cognitive load — one set of controls, everything updates. Inline controls handle chart-specific options without cluttering the filter bar. No second sidebar eating horizontal space.

## 2025-02-04: Color theme — Keep purple

**Context:** Considered switching to a neutral Grafana-like palette.
**Decision:** Keep the purple brand accent (#7C2A83) with department colors (Lacey blue, Centralia red, Aberdeen green). Apply Grafana-style light mode aesthetics (clean white cards, light gray page background, minimal borders).
**Why:** The purple is already associated with the RadiantCare brand. The visual refresh comes from layout and component quality, not a new color.

## 2025-02-04: Maps — Plotly Mapbox

**Context:** Need geographic maps for Patients and Referrals pages.
**Decision:** Plotly Mapbox (scatter maps, flow lines). Requires free Mapbox API token.
**Why:** Native Plotly integration means it works seamlessly in Dash callbacks. Built-in interactivity (zoom, pan, hover). Light map style matches the dashboard aesthetic.

## 2025-02-04: Data source — Read from OneDrive directly

**Context:** Data lives in automated ARIA exports on OneDrive. Could copy to local, build a pipeline, or read in place.
**Decision:** App reads from `/Users/Mike/Library/CloudStorage/OneDrive-ProvidenceSt.JosephHealth/AURA_Reports/` directly. Pipeline architecture (app-handled vs separate script) deferred.
**Why:** OneDrive syncs automatically. No reason to duplicate data. Pipeline decision can wait until we understand startup performance with the full dataset.

## 2025-02-04: Project structure — Rebuild in place

**Context:** Could start a new repo, new branch, or archive and rebuild in the same directory.
**Decision:** Archive existing code to `archive/` folder, rebuild in the same project root.
**Why:** Preserves git history, keeps docs accessible, no repo management overhead. Clean separation — old code is accessible but out of the way.

## 2025-02-04: UI Library — Dash Mantine Components (DMC)

**Context:** Needed to choose between DBC (Bootstrap) and DMC (Mantine) for the rebuild.
**Decision:** Switch from DBC to DMC as the primary UI library.
**Why:** DMC provides a more modern aesthetic out of the box, built-in theming with centralized theme object, consistent component API, and better components for the dashboard use case (AppShell for sidebar layout, SegmentedControl for filter toggles, DateRangePicker). Matches the "sleeker" goal without heavy custom CSS.

## 2025-02-04: Tables — dash-ag-grid replaces dash_table

**Context:** `dash_table.DataTable` is officially deprecated by Plotly.
**Decision:** Use `dash-ag-grid` for all data tables.
**Why:** AG Grid has built-in sorting, filtering, column resizing, virtual scrolling for large datasets, and native CSV export. Significantly more capable than the deprecated `dash_table`.

## 2025-02-04: Plotly — Upgrade to v6

**Context:** Current app uses Plotly 5.18. Latest is 6.5.2.
**Decision:** Upgrade to Plotly 6.5+ for the rebuild.
**Why:** Major version jump with performance improvements and better Mapbox support.

## 2025-02-04: Pages — 13 pages confirmed

**Decision:** Home, Operations, Workflow, Clinic Visits, Simulations, Tasks, OTVs, Billing, Machine Performance, Courses, Plans, Patients, Referrals.
**Key details:**
- Home includes rolling physician census chart (from Treatment-Detail, aggregated by TreatingPhysician per day)
- Operations combines Daily Volume Past/Future + Treatment + Availability
- Tasks uses Physician Schedule as cross-reference only (no dedicated page)
- OTVs includes Weekly Visits data
- Billing includes payor mix from multiple angles (per patient, per consult, per course, per billed activity)
- Patients and Referrals both use Mapbox geographic maps
