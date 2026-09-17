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


