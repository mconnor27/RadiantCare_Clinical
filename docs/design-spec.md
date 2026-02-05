# Design Specification

## Design Philosophy

Clean, data-forward dashboard. Grafana light mode aesthetic with the existing purple brand accent. Prioritize information density without clutter. Every pixel serves the data.

---

## Color Palette

### Brand Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--primary` | `#7C2A83` | Primary accent — nav active state, buttons, links, KPI highlights |
| `--primary-light` | `#F3E8F5` | Primary tint — selected filter backgrounds, hover states |
| `--primary-dark` | `#5A1D60` | Darker accent — nav background, active page indicator |

### Department Colors

| Department | Color | Hex |
|-----------|-------|-----|
| Lacey | Blue | `#2196F3` |
| Centralia | Red | `#F44336` |
| Aberdeen | Green | `#4CAF50` |

### Neutral Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-page` | `#F5F6F8` | Page background (light gray, not pure white) |
| `--bg-card` | `#FFFFFF` | Card/panel backgrounds |
| `--bg-nav` | `#1E1E2D` | Navigation sidebar background (dark) |
| `--bg-nav-hover` | `#2A2A3D` | Nav item hover |
| `--bg-filter-bar` | `#FFFFFF` | Filter bar background |
| `--border` | `#E0E0E0` | Card borders, dividers |
| `--border-light` | `#F0F0F0` | Subtle separators |
| `--text-primary` | `#1A1A2E` | Primary text (near-black) |
| `--text-secondary` | `#6B7280` | Secondary/label text |
| `--text-muted` | `#9CA3AF` | Muted text, placeholders |
| `--text-nav` | `#A0A4B8` | Nav text (inactive) |
| `--text-nav-active` | `#FFFFFF` | Nav text (active) |

### Semantic Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--success` | `#10B981` | Pass, OK, positive indicators |
| `--warning` | `#F59E0B` | Caution, approaching threshold |
| `--error` | `#EF4444` | Fail, overdue, negative indicators |
| `--info` | `#3B82F6` | Informational highlights |

### Chart Color Sequence

For multi-series charts where department colors don't apply, use this sequence:

```
#7C2A83  (purple - primary)
#2196F3  (blue)
#F44336  (red)
#4CAF50  (green)
#FF9800  (orange)
#00BCD4  (cyan)
#9C27B0  (violet)
#795548  (brown)
```

---

## Typography

| Element | Font | Size | Weight | Color |
|---------|------|------|--------|-------|
| Page title | System sans-serif | 20px | 600 | `--text-primary` |
| Section header | System sans-serif | 16px | 600 | `--text-primary` |
| Card title | System sans-serif | 14px | 500 | `--text-secondary` |
| KPI value | System sans-serif | 28px | 700 | `--text-primary` |
| KPI label | System sans-serif | 12px | 400 | `--text-secondary` |
| Body text | System sans-serif | 14px | 400 | `--text-primary` |
| Table header | System sans-serif | 12px | 600 | `--text-secondary` |
| Table cell | System sans-serif | 13px | 400 | `--text-primary` |
| Filter label | System sans-serif | 12px | 500 | `--text-secondary` |
| Nav item | System sans-serif | 13px | 500 | `--text-nav` |

Use system font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

---

## Layout

### Overall Structure

```
┌─────────┬──────────────────────────────────────────────────┐
│   NAV   │                  CONTENT AREA                    │
│ SIDEBAR │                                                  │
│         │  ┌────────────────────────────────────────────┐  │
│  60px   │  │         FILTER BAR (optional)              │  │
│  wide   │  └────────────────────────────────────────────┘  │
│ (icon)  │                                                  │
│         │  ┌────────────────────────────────────────────┐  │
│  200px  │  │              PAGE CONTENT                  │  │
│  wide   │  │          (charts, tables, KPIs)            │  │
│ (open)  │  │                                            │  │
│         │  └────────────────────────────────────────────┘  │
└─────────┴──────────────────────────────────────────────────┘
```

### Dimensions

| Element | Value |
|---------|-------|
| Nav sidebar (expanded) | 200px wide |
| Nav sidebar (collapsed) | 60px wide (icons only) |
| Content area padding | 24px |
| Filter bar height | 56px |
| Card gap (grid) | 16px |
| Card padding | 20px |
| Card border-radius | 8px |
| Card shadow | `0 1px 3px rgba(0,0,0,0.08)` |
| KPI card min-height | 100px |
| Chart card min-height | 300px |
| Page max-width | None (fluid, fills available space) |

### Grid System

Use a 12-column grid within the content area. Common layouts:

| Pattern | Description |
|---------|-------------|
| 4 x 3-col | Four KPI cards in a row |
| 3 x 4-col | Three KPI cards in a row |
| 2 x 6-col | Two charts side-by-side |
| 1 x 12-col | Full-width chart or table |
| 8-col + 4-col | Main chart with smaller side chart |
| 6-col + 6-col over 12-col | Two charts on top, full-width table below |

---

## Navigation Sidebar

### Structure

```
┌─────────────────────┐
│  ☰  RadiantCare      │  ← Logo/brand + collapse toggle
├─────────────────────┤
│  🏠  Home            │
│  📊  Operations      │
│  🔄  Workflow        │
│  🏥  Clinic Visits   │
│  📡  Simulations     │
│  ✅  Tasks           │
│  📋  OTVs            │
│  💰  Billing         │
│  ⚙️  Machines        │
│  📦  Courses         │
│  📐  Plans           │
│  👥  Patients        │
│  🔗  Referrals       │
├─────────────────────┤
│  ❓  Help            │  ← Bottom-pinned
│  ⚙️  Settings        │
└─────────────────────┘
```

**Note:** Icons above are placeholders. Use Font Awesome icons in implementation. Do not use emojis.

### Behavior

- Default state: expanded (200px) on desktop
- Toggle to collapsed (60px, icons only) via button at top
- Collapsed shows icon + tooltip on hover
- Active page: white text, left border accent (`--primary`), subtle background (`--bg-nav-hover`)
- Inactive page: muted text (`--text-nav`)
- Hover: background shifts to `--bg-nav-hover`

---

## Filter Bar

Sits at the top of the content area, inside a white card. Contains page-level filters that apply to ALL charts on the page.

### Standard Filters

Most pages will have some combination of:

| Filter | Control Type | Default |
|--------|-------------|---------|
| Date range | Date picker (start/end) or preset buttons (YTD, Last 12mo, All) | Last 12 months |
| Department | Multi-select checkboxes or pills | All selected |
| Physician | Multi-select dropdown | All selected |

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Date Range: [YTD] [12mo] [All] [Custom ▾]    Dept: [L] [C] [A]    MD: [All ▾]    [Apply] │
└─────────────────────────────────────────────────────────────────┘
```

- Filters are horizontal, left-aligned
- Apply button on the right (or auto-apply on change — decide per page)
- Department filters use department colors as pill/chip backgrounds
- Compact — one row, 56px height

---

## Components

### KPI Card

A small card showing a single metric.

```
┌──────────────────────┐
│  Total Treatments     │  ← label (--text-secondary, 12px)
│  1,247               │  ← value (--text-primary, 28px, bold)
│  ▲ 8.2% vs prior     │  ← trend (--success or --error, 12px)
└──────────────────────┘
```

- Background: `--bg-card`
- Border: 1px `--border`
- Border-radius: 8px
- Shadow: card shadow
- Padding: 20px
- Optional: colored left border (4px) using `--primary` or semantic color
- Optional: trend indicator with up/down arrow and comparison text

### Chart Card

A card containing a Plotly chart with optional inline controls.

```
┌──────────────────────────────────────────────────────┐
│  Treatment Volume by Location          [Line ▾] [⋮]  │  ← title + inline controls
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │                                                 │ │
│  │              PLOTLY CHART                       │ │
│  │                                                 │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- Title row: card title left, inline controls right
- Inline controls: small dropdowns or toggles for chart-specific options (e.g., chart type, grouping, smoothing)
- These are chart-specific and do NOT go in the page-level filter bar
- Chart fills the card with consistent padding
- Same card styling as KPI cards

### Data Table

```
┌──────────────────────────────────────────────────────┐
│  Simulation Summary                    [Export CSV]   │
├──────────┬────────────┬──────────┬──────────────────┤
│  Date    │  Patient   │  Type    │  Duration (min)  │
├──────────┼────────────┼──────────┼──────────────────┤
│  01/15   │  SMITH, J  │  Initial │  60              │
│  01/15   │  DOE, A    │  SRS     │  90              │
└──────────┴────────────┴──────────┴──────────────────┘
```

- Header row: bold, uppercase, `--text-secondary`
- Alternating row backgrounds: white / `#FAFAFA`
- Hover: row highlights with `--primary-light`
- Sortable columns indicated by ↕ icon
- Optional CSV export button in card title row
- Same card wrapper as chart cards

### Sankey / Flow Diagram

For the Workflow page. Full-width card, taller than standard charts.

```
┌──────────────────────────────────────────────────────┐
│  Patient Workflow Pipeline                            │
│                                                       │
│  Consult ──→ Simulation ──→ Draw ──→ Plan ──→ Treat  │
│  (width proportional to volume at each stage)         │
│                                                       │
│  Min height: 500px                                    │
└──────────────────────────────────────────────────────┘
```

- Use Plotly Sankey (`go.Sankey`)
- Node colors follow the chart color sequence
- Link colors: translucent version of source node color
- Hover shows volume and timing metrics

### Map

For Patients and Referrals pages.

```
┌──────────────────────────────────────────────────────┐
│  Patient Origins                         [Zoom ▾]    │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │                                                 │ │
│  │           MAPBOX SCATTER / FLOW MAP             │ │
│  │                                                 │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- Use Plotly Mapbox (`px.scatter_mapbox` or `go.Scattermapbox`)
- Light map style (Mapbox light or streets)
- Department locations as fixed markers with department colors
- Patient origins as scatter points or choropleth by ZIP/county
- Flow lines from origin to department using `go.Scattermapbox` lines
- Requires `MAPBOX_TOKEN` environment variable

---

## Chart Conventions

### Axes

- X-axis label: below chart, `--text-secondary`
- Y-axis label: rotated, left of chart, `--text-secondary`
- Grid lines: light (`#F0F0F0`), horizontal only (no vertical grid)
- Axis lines: `--border`
- Tick labels: `--text-muted`, 11px

### Plotly Layout Defaults

```python
DEFAULT_LAYOUT = dict(
    font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
    plot_bgcolor="#FFFFFF",
    paper_bgcolor="#FFFFFF",
    margin=dict(l=48, r=16, t=32, b=48),
    xaxis=dict(
        gridcolor="#F0F0F0",
        linecolor="#E0E0E0",
        showgrid=False,
    ),
    yaxis=dict(
        gridcolor="#F0F0F0",
        linecolor="#E0E0E0",
        showgrid=True,
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        font=dict(size=12),
    ),
    hoverlabel=dict(
        bgcolor="#FFFFFF",
        bordercolor="#E0E0E0",
        font=dict(size=13, color="#1A1A2E"),
    ),
    colorway=[
        "#7C2A83", "#2196F3", "#F44336", "#4CAF50",
        "#FF9800", "#00BCD4", "#9C27B0", "#795548",
    ],
)
```

### Time Series

- Default: line chart with markers off (clean lines)
- LOWESS smoothing optional — controlled via inline slider on the chart card
- Show mean/median as horizontal dashed lines when relevant
- Date format on x-axis: `%b %Y` for monthly, `%m/%d` for daily

### Bar Charts

- Vertical bars, rounded top corners (2px radius)
- Grouped bars for comparison (side-by-side, not stacked) by default
- Stacked only when showing composition (e.g., technique mix)

### Hover

- Clean white tooltip with border
- Show relevant context (date, value, category)
- No redundant information (don't repeat what's obvious from the axis)

---

## Responsive Behavior

| Breakpoint | Nav | Grid | Filter bar |
|-----------|-----|------|-----------|
| > 1400px | Expanded (200px) | Full grid layouts | Single row |
| 1024-1400px | Collapsed (60px) | 2-col max for charts | Single row, may wrap |
| < 1024px | Hidden (hamburger toggle) | Single column | Stacked vertically |

---

## Page Layout Templates

### Template A: KPI + Charts + Table (most pages)

```
┌─────────────────────────────────────────────────────────┐
│  Filter Bar                                              │
├────────┬────────┬────────┬────────┬────────┬────────────┤
│  KPI   │  KPI   │  KPI   │  KPI   │  KPI   │  KPI      │
├────────┴────────┴────────┼────────┴────────┴────────────┤
│                          │                               │
│     Chart (6-col)        │      Chart (6-col)           │
│                          │                               │
├──────────────────────────┴───────────────────────────────┤
│                                                          │
│                  Full-width Table                        │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Template B: Full-width Feature (Workflow, Maps)

```
┌─────────────────────────────────────────────────────────┐
│  Filter Bar                                              │
├────────┬────────┬────────┬───────────────────────────────┤
│  KPI   │  KPI   │  KPI   │  KPI                         │
├────────┴────────┴────────┴───────────────────────────────┤
│                                                          │
│               Full-width Sankey / Map                    │
│                       (500px+)                           │
│                                                          │
├──────────────────────────┬───────────────────────────────┤
│     Supporting Chart     │     Supporting Chart          │
└──────────────────────────┴───────────────────────────────┘
```

### Template C: Operations (Calendar / Timeline)

```
┌─────────────────────────────────────────────────────────┐
│  Filter Bar                                              │
├────────┬────────┬────────┬───────────────────────────────┤
│  KPI   │  KPI   │  KPI   │  KPI                         │
├────────┴────────┴────────┴───────────────────────────────┤
│                                                          │
│     Horizontal Timeline / Band Chart (full width)        │
│                                                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│     Detail Table (sortable, filterable)                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Interaction Patterns

### Filter Apply Behavior

- Department and physician filters: apply immediately on change (no Apply button needed for simple toggles)
- Date range: apply on selection for presets (YTD, 12mo), apply button for custom range
- All charts on the page update simultaneously when page-level filters change

### Chart Inline Controls

- Small, unobtrusive — positioned in the chart card title bar
- Examples: chart type toggle (line/bar), grouping dropdown (by dept/by MD), smoothing slider
- These only affect the individual chart, not other charts on the page

### Loading States

- Show a subtle spinner or skeleton placeholder while charts load
- Never show a blank white card — always show loading or empty state
- Empty state: centered gray text "No data for selected filters"

### Navigation

- URL routing: each page has a URL path (`/`, `/operations`, `/workflow`, etc.)
- Browser back/forward works
- Filter state preserved in URL query params or session store when navigating between pages

---

## Header

Minimal. The nav sidebar handles navigation, so the header is either:
- **Not needed** (Grafana-style — the nav sidebar IS the header)
- **Thin strip** showing just the current page title and help icon

Recommended: no separate header. Page title appears at the top of the content area, left-aligned, with the help icon to its right.

```
┌─────────────────────────────────────────────────────┐
│  Operations                              [?] [⚙️]    │  ← page title + help + settings
├─────────────────────────────────────────────────────┤
│  Filter bar...                                       │
```
