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


