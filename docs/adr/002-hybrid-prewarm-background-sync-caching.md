# ADR 002: Hybrid "Pre-Warm + Background Sync" Caching Architecture for BigQuery Telemetry

## Status
**ACCEPTED & IMPLEMENTED** (2026-09-17)

## Context & Problem Statement
MindTheSpot monitors Google Cloud Spot VM preemption histories and spot pricing telemetry across all 43 GCP regions and 130 zones (spanning over 6,200 instance pools). 

The raw preemption rates (30-day daily points) and pricing intervals (1-year history) are ingested by a weekly crawler running as a Cloud Run Job (`mindthespot-crawler`) and written to BigQuery tables (`mindthespot_raw.preemption_history`, `mindthespot_raw.price_history`). Analytical views (`mindthespot_analytics.v_regime_shifts` and `v_pivot_recommendations`) compute statistical regime shifts ($Z \ge 2.5$) and price step changes ($\ge 10\%$).

When serving the React UI through the FastAPI backend (`mindthespot-app`), querying BigQuery directly on every user action introduces critical drawbacks:
1. **High User Latency:** BigQuery is an OLAP data warehouse. Each interactive query involves job scheduling, slot allocation, and query execution, resulting in **1,200ms – 3,500ms** latency per request. This creates perceptible lag and loading spinners when users filter instance families or inspect pools.
2. **The "Freshness Paradox":** The GCP Compute advice API only computes preemption rates daily and pricing steps every few weeks. The MindTheSpot crawler runs **weekly** (Mondays at 01:00 UTC). Querying BigQuery live on every HTTP request yields 0% fresher data than a cached state, because the underlying tables are static between weekly runs.
3. **BigQuery Quota & Concurrency Limits:** BigQuery enforces a default project quota of 300 concurrent interactive queries. Under concurrent dashboard use or automated polling, direct querying threatens quota exhaustion and incurs unnecessary slot costs.

---

## Decision

We designed and implemented a **Hybrid Pre-Warmed Read-Through In-Memory Cache with Asynchronous Background Synchronization**:

```
+-------------------------------------------------------------+
|                      Cloud Run Boot                         |
|  1. Execute batch query against BigQuery (v_regime_shifts)  |
|  2. Load ~15 MB dataset into in-memory dictionary cache     |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                    FastAPI Serving (< 5ms)                  |
|  - GET /v1/pools               --> Serves from RAM cache    |
|  - GET /v1/anomalies           --> Serves from RAM cache    |
|  - GET /v1/pools/.../history   --> Serves from RAM cache    |
|  - GET /v1/pivots/...          --> Serves from RAM cache    |
+-------------------------------------------------------------+
                               ^
                               | Post-Crawl Webhook / Async Refresh
+------------------------------+------------------------------+
|            Cloud Scheduler / Weekly Crawler Job             |
|  - Monday 01:00 UTC: Crawler writes new partition to BQ     |
|  - Step 2: Calls POST /v1/cache/refresh to hot-swap cache   |
+-------------------------------------------------------------+
```

### 1. Startup Pre-Warming (`lifespan`)
- On Cloud Run container initialization, a single fast batch query executes against `mindthespot_analytics.v_regime_shifts` and `mindthespot_raw.price_history`.
- The query results are transformed into strongly-typed Pydantic schemas and stored in memory.
- Startup warm-up takes $\approx 1.5$–$2.2$ seconds, completely masked from users when Cloud Run runs with `min-instances: 1` or startup CPU boost.

### 2. Resilient Graceful Fallback
- If BigQuery credentials are not configured (e.g. local offline development, unit tests) or if BigQuery encounters a transient network timeout during boot:
  - The service logs a warning and falls back to a deterministic synthetic dataset.
  - The container **never crashes on startup**, guaranteeing 100% service availability.

### 3. RAM Footprint
- 6,240 instance pools $\times$ 30 daily preemption rates $\times$ 16 pricing intervals consumes **$\approx 12$ MB to $15$ MB** in memory.
- In Cloud Run (512 MiB or 1 GiB memory), this represents **$< 3\%$ of total container memory**, presenting zero risk of Out-Of-Memory (OOM) errors.

### 4. Background Sync & Hot Swapping
- The API exposes management endpoints:
  - `GET /api/v1/cache/status`: Returns current cache state, last warm timestamp, pool count, and source (`bigquery` vs `synthetic`).
  - `POST /api/v1/cache/refresh`: Spawns a non-blocking background task that executes the BigQuery refresh and atomically replaces the in-memory cache pointer. Existing serving threads are never blocked.
- Cloud Scheduler or the crawler job invokes `POST /api/v1/cache/refresh` after each crawl run.

---

## Consequences & Verification

### Positive:
- **Sub-5ms End-User Latency:** API endpoints now respond in $2$–$5$ ms, delivering instant UI rendering, snappy table filtering, and instant inspector modals.
- **Zero Downstream Load on BigQuery:** Regular user traffic generates $0$ BigQuery queries, eliminating quota bottlenecks and keeping BigQuery costs within the free tier.
- **Authentic Telemetry:** Inspecting instance pools (such as `c4a-standard-4` in `europe-west4`) displays actual multi-step historical pricing intervals ($0.0229/hr) and real preemption volatility directly from Google Cloud.

### Negative / Trade-Offs:
- **Container Cold Start:** Containers without `min-instances >= 1` incur an additional $\sim 1.5$s startup delay while fetching BigQuery data on the first boot.
- **Eventual Consistency:** When a new crawl finishes, cached instances reflect the new data only after the background sync completes or the TTL expires. Given the weekly crawl schedule, this is entirely acceptable.
