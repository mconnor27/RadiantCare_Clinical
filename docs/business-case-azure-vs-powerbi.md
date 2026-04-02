# Business Case: RadiantCare Clinical Dashboard — Azure Deployment vs. Power BI Rebuild

## Executive Summary

We have a fully built, production-ready clinical operations dashboard for Radiation Oncology. Deploying it requires a single Azure Web App that costs **$0–13/month** and takes **one afternoon**. Rebuilding it in Power BI would cost an estimated **$15,000–40,000** in development labor, take **months**, and deliver an inferior product with permanent feature gaps. Azure App Service is a first-party Microsoft service on infrastructure we already pay for — this is not adopting "another thing."

---

## What This App Actually Requires

This is an extraordinarily lightweight application:

| Requirement | Detail |
|---|---|
| **Runtime** | Python + 11 open-source packages |
| **Database** | None |
| **External APIs** | None (Mapbox token for 2 map pages — free tier) |
| **Authentication** | Can use existing Azure AD / SSO |
| **Storage** | Reads CSV files already synced via OneDrive |
| **Compute** | Single-threaded web server; 5–10 concurrent users max |

There is no database to manage, no message queue, no microservices, no container orchestration. It's a Python script that reads CSV files and renders charts in a browser.

### Azure Hosting Options

| Azure Tier | Monthly Cost | Specs | Sufficient? |
|---|---|---|---|
| **F1 (Free)** | **$0/month** | Shared CPU, 1 GB RAM, 1 GB storage | Yes — for light use during evaluation |
| **B1 (Basic)** | **~$13/month** | 1 core, 1.75 GB RAM, 10 GB storage | Yes — comfortably handles the department |

For context, **$13/month** is less than a single Power BI Pro license.

### Deployment Steps (Total: ~2–4 hours)

1. `az webapp create` — provision an App Service (~5 min)
2. `az webapp up` — deploy the code (~5 min)
3. Set 2 environment variables (Mapbox token, data path) (~5 min)
4. Point the data directory to an Azure file share or Blob container synced from the existing OneDrive export (~1–2 hours, one-time)
5. Done

No build pipeline. No CI/CD required (though it can be added trivially via GitHub Actions). No infrastructure diagram needed — it's one box.

---

## This Is a Microsoft Service, Not "Another Thing"

Azure App Service is:
- A **first-party Microsoft PaaS product**
- Managed under the **same Azure subscription** the organization already pays for
- Covered by the **same enterprise support agreements**
- Subject to the **same security, compliance, and governance policies** as every other Azure resource

Hosting a web app on Azure App Service is no different from hosting a SharePoint site or a Power Automate flow — it's using the Microsoft platform we already own. The directive to "use existing solutions" is exactly what this does.

---

## Power BI Licensing vs. Azure Web App

Power BI requires per-user licensing for anyone who views a dashboard:

| Scenario | Power BI Cost | Azure Web App Cost |
|---|---|---|
| 10 viewers | $100/month ($10/user) | $0–13/month |
| 30 viewers | $300/month | $0–13/month |
| 50 viewers | $500/month | $0–13/month |
| Department-wide (Premium) | ~$5,000/month | $0–13/month |

The web app is a URL. Anyone with network access and a browser can use it — physicians, therapists, physicists, managers — with **zero per-user cost**. Deploying on Azure actually **reduces** Microsoft licensing spend compared to Power BI.

---

## The Rebuild Cost Is the Real Issue

### What already exists (and would need to be recreated)

| Component | Scale |
|---|---|
| Pages of interactive dashboards | **17** |
| Interactive callbacks (filter/chart logic) | **129** |
| Lines of application code | **33,000+** |
| Lines of data processing logic | **658** (loader alone) |
| Data sources integrated | **13 ARIA CSV exports** |
| Custom JavaScript modules | **7** (clientside interactivity) |

### Estimated Power BI rebuild effort

| Phase | Hours | Notes |
|---|---|---|
| Data modeling & Power Query ETL | 80–120 | Reverse-engineering ARIA incremental file assembly, composite dedup keys, column normalization, 7-stage workflow chain construction |
| Dashboard page recreation (17 pages) | 100–160 | Many visualizations have no Power BI equivalent and would need to be simplified or cut |
| DAX measures & KPI logic | 40–60 | Date-relative calculations, rolling averages, business-hours logic, counting semantics (sessions vs. patients vs. courses) |
| Testing & validation | 40–60 | Verifying numbers match current dashboard across all pages |
| **Total** | **260–400 hours** | |

At **$75–100/hour** for Power BI consulting (conservative), that's **$19,500–$40,000** — to produce something worse.

### What gets lost in a Power BI rebuild

These features have **no Power BI equivalent**:

- **Clientside interactivity** — The dashboard performs real-time LOWESS smoothing, chart type switching, and date range animations entirely in the browser with zero server round-trip. Power BI visuals re-query the dataset on every filter change.

- **Workflow pipeline visualization** — Radiation oncology treatments flow through 7 stages (Exam → Simulation → Draw → Contour Review → Isodose → Review Plan → Treatment) with loopbacks when patients are re-simulated or re-planned. This requires custom Gantt-style rendering that Power BI doesn't support.

- **Custom geographic mapping** — Interactive Mapbox-powered patient origin and referral maps with clustering and custom layers. Power BI maps are limited to basic pins and filled regions.

- **Server-side data protection** — Patient-level data is aggregated server-side before anything reaches the browser. Power BI pushes row-level data to the client (RLS restricts access but data still transits the network).

- **Version-controlled logic** — Every line of data processing is in Git: reviewable, auditable, diffable. Power BI `.pbix` files are opaque binaries. When a number looks wrong, there's no `git blame` to trace why.

---

## Risk Comparison

| Risk | Azure Web App | Power BI Rebuild |
|---|---|---|
| Deployment fails | Low — standard Azure PaaS, well-documented | N/A |
| Rebuild takes longer than estimated | N/A — already built | **High** — ARIA data complexity is non-obvious; ETL alone could take months |
| Data accuracy issues | Low — current logic is validated and in production | **High** — recreating 658 lines of loader logic in Power Query invites subtle bugs |
| Ongoing maintenance burden on IT | Minimal — no database, no patching, auto-restart | Moderate — Power BI dataset refreshes, gateway management, license administration |
| Staff adoption | Already in use | Retraining required; reduced functionality may frustrate users |

---

## Summary

| | Azure Web App | Power BI Rebuild |
|---|---|---|
| **Monthly cost** | $0–13 | $100–5,000 (licensing) |
| **Deployment effort** | 2–4 hours | 260–400 hours ($19,500–40,000) |
| **Feature parity** | Full (it's the existing app) | Partial — permanent gaps |
| **IT support burden** | Near zero | Ongoing (gateway, licensing, refresh schedules) |
| **Platform** | Microsoft Azure | Microsoft Power BI |
| **Per-user licensing** | None | Required |
| **Data auditability** | Git-tracked Python | Opaque .pbix binaries |

**The question is not "why not Power BI?" It's "why would we spend $20,000+ and months of work to rebuild something worse, when we can deploy what already exists on the same Microsoft platform for $13/month and an afternoon?"**
