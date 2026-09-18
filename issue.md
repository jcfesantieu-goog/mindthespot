# Issue Tracker: Cloud Run Crawler Job OOM Crash (Signal 9) on 43-Region Ingestion

## Status
**RESOLVED** (2026-09-17)

## Incident Overview
During the execution of the Cloud Run Job `mindthespot-crawler` in project `jcf-mindthespot` (region `europe-west4`) for full 43-region telemetry ingestion, Task 0 repeatedly crashed after approximately 2 minutes of execution with an Out-Of-Memory (OOM) error:

```json
{
  "insertId": "6aabdd200007a472aea847b2",
  "logName": "projects/jcf-mindthespot/logs/run.googleapis.com%2F%2Fvar%2Flog%2Fsystem",
  "receiveTimestamp": "2026-09-17T12:29:20.505526415Z",
  "textPayload": "Out-of-memory event detected in container",
  "timestamp": "2026-09-17T12:29:20.500850Z"
}
```

### Timeline
- **14:27:12 CEST**: Job execution initiated (`🚀 Starting MindTheSpot Crawler (Project: jcf-mindthespot, Dataset: mindthespot_raw)...`).
- **14:29:20 CEST** (+128s): `Out-of-memory event detected in container` -> `Container terminated on signal 9` (cgroup limit `2Gi` exceeded).
- **14:29:34 CEST**: Retry attempt 1 starts.
- **14:32:40 CEST** (+186s): Second `Out-of-memory event detected in container` -> `Container terminated on signal 9`.
- **Completion Status**: `EXECUTION_FAILED`.

---

## Root-Cause Analysis

MindTheSpot catalogs **6,240 instance pools** across 43 regions (130 zones) and **2,064 unique regional machine types**, totaling **8,304 API calls** per crawl cycle.

The OOM crash was driven by **four compounding bottlenecks** acting simultaneously:

### 1. Unbounded Task Spawning (`extractor.py`)
`CrawlEngine.run()` generated 6,240 preemption tasks and 2,064 price tasks into list comprehensions and passed all 8,304 coroutines to `asyncio.gather(*tasks)` all at once. All 8,304 coroutines were instantiated on the heap simultaneously, each allocating stack context, frame objects, and parameter bindings.

### 2. Per-Request `httpx.AsyncClient` Allocation (`client.py`)
In `GCPCapacityHistoryClient._send_request_with_backoff`, `self.http_client` defaulted to `None`. For each request, a new `httpx.AsyncClient(http2=True, timeout=30.0)` was instantiated **prior** to entering the rate limiter.
Consequently, **8,304 independent `httpx.AsyncClient` instances** were allocated on the heap concurrently. Each client carries:
- An HTTP/2 connection pool (`httpcore.AsyncConnectionPool`)
- SSL Context and socket wrappers
- Internal read/write buffers and state machines
At $\approx 250$–$350$ KB per client, $8,304 \times 300\text{ KB} \approx \mathbf{2.49\text{ GB}}$ of memory was allocated within the first 60 seconds.

### 3. Semaphore Trapping & GCE Metadata Server Token Storm
In `rate_limiter.py`, `AsyncTokenBucketRateLimiter` enforces `max_concurrency = 10`.
The first 10 tasks entered the network call, while the remaining **8,294 tasks were blocked in memory on `await self.semaphore.acquire()`**.
Crucially, while waiting, each blocked task **retained its fully instantiated `httpx.AsyncClient` in memory**.
Furthermore, each task invoked `google.auth.default()` and refreshed OAuth credentials without caching, resulting in thousands of concurrent calls flooding the GCE metadata server (`169.254.169.254`), causing buffer bloat and latency spikes.

### 4. Monolithic In-Memory Telemetry Accumulation (`cli.py`)
`CrawlEngine.run()` retained all 6,240 `PreemptionSnapshotRecord`s (187,200 daily points) and 2,064 `PriceSnapshotRecord`s (~33,000 intervals) in memory until the entire crawl concluded.
Before loading into BigQuery, `cli.py` transformed all 220,000 records into a second list of dictionaries, doubling heap usage during JSON serialization.

---

## Fix Proposition & Architecture

We propose a 5-pillar optimization reducing memory consumption from **$> 2.5\text{ GB}$ to $< 120\text{ MB}$ ($> 95\%$ reduction)**:

```
[ Catalog: 43 Regions / 6,240 Pools ]
                  |
                  v
[ Bounded Worker Queue: 15 Workers ] <---> [ Singleton Shared httpx.AsyncClient Session ]
                  |                                     |
                  |                                     +---> [ Cached OAuth2 Token (1h TTL) ]
                  v
[ Region-by-Region Streaming Ingestion ]
  1. Fetch Region A (e.g. europe-west4, ~150 pools)
  2. Batch insert rows to BigQuery (preemption_history & price_history)
  3. Purge Region A from heap / trigger GC
  4. Repeat for Region B ...
```

### Pillar 1: Shared `httpx.AsyncClient` Session with Connection Pooling
- Equip `GCPCapacityHistoryClient` with an async context manager lifecycle (`async with GCPCapacityHistoryClient() as client:`).
- Reuse a single `httpx.AsyncClient(http2=True, limits=httpx.Limits(max_keepalive_connections=20, max_connections=30))` across all 8,304 requests.
- Memory allocation drops from 8,304 clients ($\approx 2.5\text{ GB}$) to **1 client ($\approx 5\text{ MB}$)**.

### Pillar 2: OAuth2 Token Caching with Auto-Refresh
- Cache the OAuth access token and expiry time in `GCPCapacityHistoryClient`.
- Reuse valid tokens for subsequent calls; only refresh when expired or within 60 seconds of expiration (standard Google tokens have 3,600s TTL).
- Eliminates 8,300 redundant metadata server network calls and object allocations.

### Pillar 3: Bounded Task Queue via Worker Pool (`asyncio.Queue`)
- Instead of scheduling 8,304 coroutines simultaneously via `asyncio.gather(*all_tasks)`, feed target descriptors into an `asyncio.Queue`.
- Spawn a fixed pool of $N$ workers (e.g., $N = 15$, matching the 15 req/sec rate limit).
- At any given millisecond, only 15 coroutines exist on the heap. Heap footprint for task scheduling drops to **$< 1\text{ MB}$**.

### Pillar 4: Region-by-Region Streaming Ingestion into BigQuery
- In `CrawlEngine`, process targets **region by region** (or in chunks).
- When a region completes:
  1. Stream/flush preemption and price rows directly to BigQuery via `storage.insert_preemption_rows()` and `storage.insert_price_rows()`.
  2. Clear the records from memory and release references for garbage collection.
- Peak in-memory telemetry drops from 220,000 rows to just $\approx 4,500$ rows ($\approx 10\text{ MB}$).

### Pillar 5: Cloud Run Job Memory Headroom
- Maintain Cloud Run Job memory limit at `2Gi` (or optionally `4Gi`).
- With peak memory $< 120\text{ MB}$, the container operates with $> 16\times$ safety margin.

---

## Action Items & Checklist

- [x] **Document Issue**: Create `issue.md` detailing root cause and fix proposition.
- [x] **Shared HTTP Client & Token Cache**: Update `mindthespot/crawler/client.py` with singleton `httpx.AsyncClient`, connection pooling, lifecycle manager, and token caching.
- [x] **Bounded Regional Execution**: Refactor `mindthespot/crawler/extractor.py` to group targets and process region-by-region.
- [x] **Region Streaming Ingestion**: Update `CrawlEngine.run` with `on_region_complete` streaming callback and `mindthespot/cli.py` to flush each region to BigQuery immediately and reclaim memory.
- [x] **Test & Verification**: Added unit tests in `tests/test_crawler.py` covering shared session, token caching, and regional streaming. 45/45 tests passing with 91% code coverage (100% on `extractor.py`).
- [x] **Sync & Deploy**: Committed (`e313c7c`), pushed to `main`, and deployed via GitOps CI/CD pipeline (GitHub Actions run `35234464388`).
- [x] **Production Verification**: Triggered Cloud Run job execution `mindthespot-crawler-jdjpb` in `europe-west4`. Real-time region streaming confirmed directly inserting into BigQuery without OOM (`< 100 MB` memory footprint).

---

# Issue #2: Preemption History Truncation Due to Multi-Day Compressed Intervals & False Critical Alerts

**Status:** Resolved  
**Severity:** High (Data Fidelity & Anomaly Metric Integrity)  
**Reported:** 2026-09-17  
**Affects:** `mindthespot/crawler/client.py`, `mindthespot/storage/bigquery_client.py`, `mindthespot/cli.py`, `sql/views/templates/v_regime_shifts.sql.tpl`, `sql/views/01_v_regime_shifts.sql`, `mindthespot/api/service.py`

---

## 1. Incident Description & Observation

During inspection of instance pool **`c4a-standard-16` in zone `europe-west1-d`** on the MindTheSpot Situation Room dashboard:
1. **Apparent Staleness**: The preemption rate history chart displayed no data points after **September 3, 2026**, despite successful daily crawler executions through **September 17, 2026** (a 14-day data gap).
2. **False Critical Regime Shift Alert**: The instance was classified as `CRITICAL` with:
   - Recent 7-Day Mean ($\mu_{\text{recent}}$): **`21.9%`**
   - Baseline Mean ($\mu_{\text{baseline}}$): **`1.5%`**
   - Rate Delta ($\Delta$): **`+20.4%`**
   - Z-score: **`+9.60σ`**
3. **Contradiction**: In reality, Google Cloud had 0.0% preemption rates for this instance family throughout the past two weeks.

---

## 2. Root Cause Analysis

### A. Google Compute Engine Capacity History API Interval Compression
Google Cloud's `compute/beta/projects/{project}/advice/capacityHistory` endpoint compresses contiguous time periods with constant preemption rates into single `[startTime, endTime)` intervals:

```json
{
  "preemptionHistory": [
    {
      "interval": {
        "startTime": "2026-09-03T07:00:00Z",
        "endTime": "2026-09-17T07:00:00Z"
      },
      "preemptionRate": 0.0
    }
  ]
}
```

### B. Crawler Start-Time Truncation
In `mindthespot/crawler/client.py`, the crawler parsed intervals using only the start timestamp:
```python
# PREVIOUS BUGGY CODE:
dt = entry.get("date") or entry.get("interval", {}).get("startTime", "")[:10]
```
For `c4a-standard-16` in `europe-west1-d`:
- Google returned a 14-day interval from `2026-09-03` to `2026-09-17` with rate `0.0`.
- The crawler extracted ONLY `2026-09-03` and discarded the subsequent 13 calendar days (`2026-09-04` through `2026-09-16`).
- As a result, BigQuery received only 9 total data points spanning August 18 to September 3, with 0 points for September 4–16.

### C. Mathematical Cascade in Analytical Window Views (`v_regime_shifts`)
BigQuery's regime shift model uses a 7-day recent window (`day_rank_desc <= 7`) and a 23-day baseline (`day_rank_desc BETWEEN 8 AND 30`):
$$\text{day\_rank\_desc} = \text{ROW\_NUMBER}() \text{ OVER} (\text{PARTITION BY pool ORDER BY telemetry\_date DESC})$$

Because 13 days of zero-rate data were missing between September 3 and September 17:
1. `day_rank_desc = 1` was September 3 (rate: 0.0).
2. `day_rank_desc = 2..7` reached all the way back to **August 25th**, picking up historical spikes:
   - Aug 28: 100% (1.0)
   - Sep 02: 50% (0.50)
   - Aug 26: 2.9% (0.029)
3. This computed a false recent average:
   $$\mu_{\text{recent}} = \frac{0.0 + 0.50 + 0.0 + 1.0 + 0.029 + 0.0 + 0.0}{7} = 21.9\%$$
4. Meanwhile, the baseline window ($8 \le \text{rank} \le 30$) was starved down to just 2 points (Aug 24: 0.0, Aug 18: 3.1%), yielding $\mu_{\text{baseline}} = 1.5\%$.
5. The resulting metric was $\Delta = +20.4\%$ and $Z = +9.60\sigma$, triggering a false `CRITICAL` anomaly banner on completely stable infrastructure.

---

## 3. Architecture & Fix Implementation

### Pillar 1: Calendar Day Interval Expansion in Crawler
Introduced `_extract_preemption_rates_from_entry(entry)` in `mindthespot/crawler/client.py`:
- Parses `interval.startTime` and `interval.endTime` into `datetime.date`.
- Generates a contiguous sequence of `DailyPreemptionRate` instances for every calendar date in $[startTime, endTime)$.
- For the `2026-09-03` to `2026-09-17` interval, this generates 14 individual zero-rate daily points (`2026-09-03`, `2026-09-04`, ..., `2026-09-16`).
- Deduplicates points and chronologically sorts rates before return.

### Pillar 2: Ingestion-Level Idempotency (`purge_snapshot`)
Added `purge_snapshot(snapshot_date: str, region: str | None = None)` in `BigQueryStorageClient` and invoked it in `cli.py` before crawl execution:
- Executes parameterized `DELETE FROM preemption_history WHERE snapshot_date = @snapshot_date [AND region = @region]`.
- Guarantees that crawler testing, manual retries, or multiple job executions within the same calendar day never produce duplicate records or inflate table partitions.

### Pillar 3: Analytical Deduplication in SQL Views & API Service
Updated `sql/views/templates/v_regime_shifts.sql.tpl`, `sql/views/01_v_regime_shifts.sql`, and `mindthespot/api/service.py`:
- Added a `deduped_preemption` CTE using:
  ```sql
  ROW_NUMBER() OVER (
    PARTITION BY region, zone, machine_type, telemetry_date
    ORDER BY crawled_at DESC
  ) AS dedup_rank
  WHERE dedup_rank = 1
  ```
- Added a corresponding `deduped_prices` CTE partitioned by `(region, machine_type, interval_start)` ordered by `crawled_at DESC`.
- Guarantees that even with legacy duplicate rows from prior ad-hoc runs, analytical queries and API cache pre-warming always process exactly one deduplicated record per pool per calendar day.

---

## 4. Verification & Validation

1. **Unit Tests**:
   - `test_extract_preemption_rates_multi_day_interval`: Verified that a 14-day interval expands into 14 distinct dates with exact rate preservation.
   - `test_fetch_preemption_history_expands_compressed_intervals`: Verified that chained multi-day intervals produce a seamless contiguous daily rate sequence.
   - `test_bigquery_storage_client_purge_snapshot`: Verified that BigQuery snapshot purges execute parameterized deletions across both raw tables.
2. **Full Test Suite**: 48/48 tests passing across the entire repository.
3. **Linting & Formatting**: 100% compliant with `ruff check .` and `ruff format .`.

---

# Issue #3: Synthetic Fallback Anomaly & BigQuery Analytical View Drift

## Status
**RESOLVED** (2026-09-18)

## Affects
- `mindthespot/api/service.py`
- `sql/views/templates/v_regime_shifts.sql.tpl`
- `terraform/bigquery.tf`
- BigQuery views: `mindthespot_analytics.v_regime_shifts`, `mindthespot_analytics.v_pivot_recommendations`

---

## 1. Incident Description & Observation
On the MindTheSpot Situation Room dashboard, two major statistical anomalies were observed:
1. **Unrealistically Low Anomaly Counts**: Exactly 10 Critical Shifts, 0 Elevated Risk, 15 Price Hikes, and 15 Price Drops across 6,240 monitored pools.
2. **Flat 1-Year Pricing Curve for Unaffected Pools**: In the Inspector modal for `c4a-standard-16` / `c4d-standard-16` in `us-east1-b`, the spot price displayed a completely flat line of `$0.6080/hr` spanning 335 days with only 2 boundary data points, contradicting real Google Cloud pricing history.

---

## 2. Root Cause Analysis
1. **Terraform Pipeline Abortion on Existing Table**:
   During the rollout of the BigQuery-backed on-demand pricing feature, table `mindthespot_raw.on_demand_pricing` was populated via the Python seeder script prior to the GitOps workflow. When GitHub Actions ran `terraform apply`, Terraform failed with:
   `Error 409: Already Exists: Table jcf-mindthespot:mindthespot_raw.on_demand_pricing`.
   This aborted the pipeline before Terraform could update the analytical views `v_regime_shifts` and `v_pivot_recommendations` in dataset `mindthespot_analytics`.
2. **Query Failure During Application Startup**:
   When Cloud Run revision `mindthespot-app-00024-q7k` booted, `warm_cache_from_bigquery()` attempted to query:
   `SELECT ..., ondemand_hourly_price, spot_discount_pct FROM {pid}.mindthespot_analytics.v_regime_shifts`
   Because `v_regime_shifts` in `mindthespot_analytics` had not received the updated column definitions, BigQuery returned:
   `400 Unrecognized name: ondemand_hourly_price at [4:32]`
3. **Silent Fallback to Hardcoded Synthetic Dataset**:
   The exception handler caught the error and called `_initialize_synthetic_dataset()`. In this synthetic fallback generator:
   - Exactly 10 pools were marked `is_critical` (hardcoded to `europe-west4 / zone-a / c4d`).
   - Exactly 0 pools were marked `is_elevated`.
   - Exactly 15 pools had synthetic hikes and 15 had synthetic drops.
   - All remaining ~6,200 pools were assigned a single flat 335-day interval at rate `unit_price * cores` (for 16 cores, `$0.038 * 16 = $0.6080/hr`).

---

## 3. Architecture & Fix Implementation
1. **State Reconciliation**: Imported `google_bigquery_table.on_demand_pricing` directly into the Terraform remote GCS state.
2. **View Synchronization**: Compiled and deployed updated view definitions `v_regime_shifts` and `v_pivot_recommendations` into dataset `jcf-mindthespot.mindthespot_analytics`.
3. **Resilient Service Configuration**:
   - Enhanced `mindthespot/api/service.py` to resolve project ID across `GCP_PROJECT_ID`, `GCP_PROJECT`, and `PROJECT_ID`.
   - Parametrized raw and analytics datasets via `BIGQUERY_DATASET_RAW` and `BIGQUERY_DATASET_ANALYTICS`.
   - Improved error logging with `logger.error(..., exc_info=True)` to record full tracebacks in Cloud Logging upon failure.

---

## 4. Verification & Validation
- **Real BigQuery Cache Pre-warm**: Successfully loaded 4,057 real pools, 20,589 historical price intervals, and 121,710 daily preemption points.
- **Genuine Pricing Dynamics**:
  - `c4a-standard-16 us-east1-b`: 17 distinct price intervals across 2026 ranging between `$0.244` and `$0.396/hr`. On-demand price: `$0.72128/hr` (50.4% spot discount).
  - `c4d-standard-16 us-east1-b`: 11 distinct price intervals across 2026 ranging between `$0.265` and `$0.322/hr`. On-demand price: `$0.7712/hr` (60.3% spot discount).
- **Accurate Metric Distributions Across Monitored Pools**:
  - **109 Critical Shifts** (48 with price hikes, 61 volume/preemption spikes)
  - **65 Elevated Risk Pools** (22 with price hikes, 43 preemption shifts)
  - **1,791 Price Hikes** and **2,162 Stable Pools**

---

# Issue #4: Cloud Run Asynchronous Pre-Warm CPU Starvation, Silent Logging, and Missing UI Provenance Telemetry

## Status
**RESOLVED** (2026-09-18)

## Severity
**High** (Production Telemetry Serving & Operational Visibility)

## Affects
- `terraform/cloud_run.tf`
- `mindthespot/api/app.py`
- `mindthespot/api/routes.py`
- `mindthespot/api/service.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `tests/test_api.py`

---

## 1. Incident Description & Observation
On the live MindTheSpot dashboard deployed to Google Cloud Argolis (`https://spot-8-232-252-55.sslip.io`):
1. **Fallback Mock Dataset Served**: The Situation Room displayed 6,240 pools, 10 critical shifts, 0 elevated risks, 15 hikes, and 15 drops—matching the exact signature of the synthetic mock generator rather than the 4,057 pools, 109 critical shifts, and 65 elevated risks in BigQuery.
2. **Missing Operational Visibility**: Cloud Logging showed zero log output from `mindthespot.api.service` or `mindthespot.api.app` on container startup, making it impossible to determine why BigQuery data was not being loaded.
3. **Static UI Badge**: The frontend displayed a static, hardcoded badge (`Live Engine (15m Cache)`) with no provenance indicator and no UI mechanism to force-refresh the cache from BigQuery.

---

## 2. Root Cause Analysis

### A. Cloud Run CPU Throttling Model & Background Daemon Starvation
On Cloud Run with CPU throttling (the default configuration where `cpu_idle = true`), container CPU is throttled to near 0% whenever no active HTTP request is being processed.

When `SYNC_PREWARM` was omitted from `terraform/cloud_run.tf`, `SpotDataService` evaluated `sync_prewarm = False`:
1. The container immediately populated the 6,240 synthetic mock pools.
2. The FastAPI lifespan startup handler returned immediately and startup probes succeeded.
3. A background daemon thread (`threading.Thread`) was spawned to query BigQuery and load rows.
4. **The Bottleneck**: As soon as startup completed, Cloud Run throttled CPU allocation to near 0%. The background thread was starved of CPU cycles and suspended mid-execution before it could download and parse the 120,000+ BigQuery rows, leaving the container serving synthetic fallback data indefinitely.

### B. Suppressed Python Standard Logging
Python's standard logging module defaults to level `WARNING` when unconfigured. Because `logging.basicConfig()` was never called in `app.py` or `cli.py`, all `logger.info()` statements across the application were silently discarded and never forwarded to Cloud Logging.

### C. Missing Cache Provenance & Invalidation Telemetry
The React frontend never called `GET /api/v1/cache/status`. The dashboard top bar displayed a static badge with no provenance indicator (`bigquery` vs `synthetic`), leaving operators with no indication of cache source and no ability to trigger a live re-warm.

---

## 3. Architecture & Fix Implementation

### Pillar 1: Synchronous Startup Pre-Warming (`SYNC_PREWARM = "true"`)
Added `SYNC_PREWARM = "true"` to container environment variables in `terraform/cloud_run.tf`:
- Cloud Run allocates 100% CPU during container startup until startup probes pass.
- Setting `SYNC_PREWARM = "true"` instructs FastAPI's `lifespan` handler to block startup probes until `warm_cache_from_bigquery()` finishes.
- The entire pre-warm completes in **8.3 seconds** (well within Cloud Run's 240s startup timeout), guaranteeing that every live request is served exclusively from authentic BigQuery data.

### Pillar 2: Structured Cloud Logging Configuration
Configured standard logging in `mindthespot/api/app.py`:
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
```
In `lifespan`, log clear success/failure diagnostics:
```python
logger.info(
    "BigQuery cache pre-warm succeeded: source=%s, pools=%d, prices=%d, preemptions=%d",
    status.source,
    status.total_pools_cached,
    status.total_price_intervals,
    status.total_preemption_points,
)
```

### Pillar 3: Cold-Start Optimization
In `mindthespot/api/routes.py`, updated `get_spot_service()` to instantiate `SpotDataService(initialize_synthetic=not sync_prewarm)`. When `SYNC_PREWARM` is enabled, synthetic dataset generation is bypassed entirely, avoiding redundant memory allocation.

### Pillar 4: Interactive React UI Cache Provenance Badge
In `frontend/src/App.tsx` and `frontend/src/lib/api.ts`:
- Replaced the static header label with a dynamic **Cache Provenance Badge**:
  - 🟢 **BigQuery Live** (`4,057 pools` • Synced `HH:MM:SS`)
  - 🟡 **Syncing BigQuery...** (active refresh)
  - 🔵 **Synthetic Mock** (development fallback)
- Clicking the badge opens a telemetry popover detailing:
  - Cache source (`bigquery` vs `synthetic`)
  - Cached pools count (`4,057`)
  - Price intervals count (`20,589`)
  - Preemption points count (`121,710`)
  - Last synced timestamp
  - **Force Refresh from BigQuery** action invoking `POST /api/v1/cache/refresh`.

### Pillar 5: Hermetic Unit Tests
Added `test_cache_status_endpoint` and `test_cache_refresh_endpoint` in `tests/test_api.py`.

---

## 4. Verification & Validation

1. **Pre-flight Quality Gates**:
   - `ruff check .`: 0 errors.
   - `pytest tests/`: 59/59 tests passing in 4.51s.
   - `npm --prefix frontend run build`: Clean build in 2.46s (zero TypeScript errors).
2. **GitOps Deployment**:
   - Committed (`47b887c`), pushed to `main`, and deployed via GitHub Actions workflow `35337295926`.
3. **Production Cloud Run Logs (`mindthespot-app-00033-vt6`)**:
   ```text
   2026-09-18 11:00:33,530 [INFO] mindthespot.api.app: Initializing MindTheSpot API application lifespan...
   2026-09-18 11:00:33,554 [INFO] mindthespot.api.app: Performing synchronous cache pre-warm from BigQuery...
   2026-09-18 11:00:33,554 [INFO] mindthespot.api.service: Pre-warming MindTheSpot cache from BigQuery in project: jcf-mindthespot
   2026-09-18 11:00:41,881 [INFO] mindthespot.api.service: Successfully pre-warmed cache from BigQuery with 4057 pools (20589 price intervals, 121710 daily rates)
   2026-09-18 11:00:41,920 [INFO] mindthespot.api.app: BigQuery cache pre-warm succeeded: source=bigquery, pools=4057, prices=20589, preemptions=121710
   INFO:     Application startup complete.
   ```
4. **Live Dashboard Verification**:
   - Live URL `https://spot-8-232-252-55.sslip.io` serves 4,057 pools, 109 critical shifts, and 65 elevated risks with the green **BigQuery Live** badge active.




