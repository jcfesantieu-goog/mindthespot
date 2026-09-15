# MindTheSpot: GCP Spot Regime Shift & Pivot Engine

## Problem Statement
**How might we** automatically detect sudden volatility shifts in Google Cloud spot preemption rates and pricing across zones and machine types, so platform and DevOps teams can proactively steer their batch and stateless workloads to stable, cost-effective alternatives before pipelines fail?

---

## Recommended Direction
Build an internal intelligence system—**MindTheSpot**—consisting of a weekly scheduled crawler (Cloud Run Job + Cloud Scheduler), a BigQuery historical analytical store, and an interactive operational dashboard. 

The system focuses on **Regime Shift Detection** rather than passive telemetry. Instead of forcing engineers to inspect hundreds of individual charts, the engine continuously benchmarks rolling 7-day preemption and pricing metrics against a 30-day baseline. When an instance pool shifts from stable to volatile (or incurs a price step-hike), it triggers an alert badge and computes a **1-click Pivot Recommendation** (suggesting sibling zones or equivalent machine families like C3D, C4D, C4A/Axion, and N2D).

The system ships with an **opinionated default catalog** (covering high-demand general-purpose and compute-optimized families across active enterprise regions), while empowering teams to define their own **custom watchlist** to track their organization's exact infrastructure footprint.

---

## Key Assumptions to Validate
- [ ] **GCP API Quota Stability:** Validate that querying ~500–1,500 combinations of `advice.capacityHistory` (covering default + custom watchlists) on a weekly Cloud Run Job finishes within 3–5 minutes without hitting project-level rate limits. *(Test with a 100-request prototype script using `google-api-python-client`)*.
- [ ] **Signal vs. Noise in Preemption Spikes:** Verify that a rolling Z-score coupled with an absolute threshold floor (e.g., $Z \ge 2.5$ AND 7-day preemption $\ge 20\%$) effectively isolates true enterprise crowding from small-sample statistical noise in smaller zones. *(Test against historical data for 5 known high-traffic vs. quiet zones)*.
- [ ] **Developer Willingness to Pivot:** Confirm that DevOps/FinOps engineers will actively reconfigure GKE nodepool manifests or Batch job templates based on the pivot recommendations. *(Interview 2 internal pipeline owners on whether they already maintain fallback node pools)*.

---

## MVP Scope

### 1. Catalog & Watchlist Configuration
* **Curated Default Catalog:**
  * **Regions:** Top enterprise hubs (`us-central1`, `us-east4`, `europe-west1`, `europe-west4`, `asia-east1`, etc.).
  * **Machine Families:** Compute & General: `c4d`, `c3d`, `c4a`/`caa` (Axion ARM), `c2`, `c3`, `n2`, `n2d`, `e2`.
* **Custom Watchlist Layer:**
  * Simple YAML/JSON configuration (or UI input) allowing teams to append custom machine types and target zones.

### 2. Ingestion Pipeline (Cloud Run Job + Cloud Scheduler)
* Python worker deployed as a Cloud Run Job triggered weekly by Cloud Scheduler.
* Fetches `advice.capacityHistory` for both `PREEMPTION` (zonal) and `PRICE` (regional).
* Streaming / batch write of partitioned snapshots into BigQuery (`mindthespot_raw.capacity_history`).

### 3. BigQuery Analytics & Regime Shift Rules
* **Preemption Regime Shift:**
  * Compares rolling 7-day average ($\mu_{7d}$) vs. 30-day baseline ($\mu_{30d}$).
  * **Alert Trigger:** $Z \ge 2.5$ AND $\mu_{7d} \ge 0.20$ OR absolute jump $\Delta \ge 0.25$.
* **Price Step-Change Detection:**
  * Compares active price interval with previous interval. Flags any price increase $\ge 10\%$.
* **Smart Pivot Engine:**
  * For flagged pools, automatically calculates the top 2 alternatives:
    1. *Zone Pivot:* Same machine type in sibling zone with preemption $< 10\%$.
    2. *Family Pivot:* Equivalent vCPU/RAM (e.g. `c3d-standard-8` $\rightarrow$ `c4d-standard-8` or `c4a-standard-8`) in same region with lower volatility and price.

### 4. Interactive Dashboard
* **Situation Room (Anomaly Feed):** Ranked cards showing active regime shifts with warning severity tags (`CRITICAL`, `ELEVATED`, `PRICE HIKE`).
* **Interactive Explorer:** Filter by Region, Zone, and Machine Family with interactive 30-day preemption curves and 1-year price interval timelines.
* **Watchlist Manager:** Filter view to "My Watched Pools" vs. "Global Defaults".

---

## Not Doing (and Why)
* **Real-time / Hourly Ingestion:** GCP computes preemption boundaries at midnight Pacific Time, and spot prices change in stepped monthly intervals. Real-time scraping adds cost and quota pressure with zero informational gain.
* **Auto-mutating Live Infrastructure (Closed-Loop CI/CD):** While attractive, automatically altering live Terraform code or GKE nodepools without human approval introduces operational risk. The MVP delivers actionable intelligence; automation can come in v2.
* **Custom Machine Types & N1 GPU/TPUs:** Explicitly unsupported by the GCP `advice.capacityHistory` API.
* **Full-Universe SKU Crawling:** Scraping all 10,000+ obscure combinations wastes quota. Scoping to curated defaults + custom watchlist captures 99% of organizational value.

---

## Open Questions
- What project or service account will host the Cloud Run Job and BigQuery dataset, and do we have the `roles/compute.viewer` role enabled on it?
- What frontend framework do you prefer for the internal dashboard (e.g., Streamlit / FastHTML for fast internal deployment on Cloud Run, or a Next.js / React web app)?
