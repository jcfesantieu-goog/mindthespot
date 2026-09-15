# Implementation Plan: MindTheSpot — GCP Spot Regime Shift & Pivot Engine

## Overview
MindTheSpot is an internal FinOps and DevOps intelligence platform designed to detect statistical regime shifts in Google Cloud Spot VM preemption rates and pricing, and automatically recommend fallback pivot pools (sibling zones and equivalent machine families like C4D, C3D, C4A/Axion, and N2D). 

This plan details the step-by-step implementation following the verified [SPEC.md](file:///Users/jcfesantieu/devlocal/mindthespot/SPEC.md), building vertically from core configuration to the async crawler, BigQuery analytical lakehouse, FastAPI backend, modern React/Tailwind/shadcn/ui frontend, and unified CLI packaging.

---

## Architectural Decisions & Trade-offs
1. **Vertical Slicing & Clear Interfaces:** Work is split into six sequential phases. Each phase provides an independently testable component with strict contracts.
2. **Asymmetric API Ingestion:** Zonal extraction for preemption rates (`locationPolicy.location: "zones/{zone}"`) and regional extraction for pricing (`regions/{region}`) via a token-bucket rate limiter ($\le 15\text{ req/s}$) to guarantee zero GCP 429 quota exhaustion.
3. **Decoupled Analytics (BigQuery Views + Python Fallback):** Real-time SQL views handle production data processing in BigQuery, while a Python analytical engine provides local verification and offline testing against synthetic time-series.
4. **Unified Cloud Run Deployment:** FastAPI serves both the JSON REST API (`/api/v1/*`) and the compiled static modern React SPA (`/*`), packaged in a single lightweight container for Cloud Run.
5. **In-Memory TTL Caching:** FastAPI utilizes a 15-minute `TTLCache` over BigQuery query results to minimize query execution costs and latency.

---

## Task List

### Phase 1: Foundations & Core Configuration (`core-config`)
- [ ] **Task 1: Project Scaffolding & Tooling Setup**
  - Setup `pyproject.toml` with dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `google-cloud-bigquery`, `cachetools`, `typer`, `pytest`, `ruff`).
  - Configure `.gitignore`, `README.md`.
  - *Verify:* `uv pip install -e ".[dev]"` succeeds and `ruff check .` passes.
- [ ] **Task 2: Catalog & Custom Watchlist Models & Loaders**
  - Implement `mindthespot/config/models.py` (Pydantic v2 schemas for catalog, watchlist, and instance targets).
  - Implement `mindthespot/config/loader.py` (YAML parser with validation and merging).
  - Create `config/default_catalog.yaml` (including C4D, C3D, C4A/Axion, C2, C3, N2, N2D, E2 across enterprise regions) and `config/watchlist.example.yaml`.
  - *Verify:* `pytest tests/test_config.py` passes.

### Checkpoint 1: Foundations Validated
- [ ] All configuration unit tests pass.
- [ ] Default catalog and custom watchlist models cleanly validate.

---

### Phase 2: Ingestion & Crawler Engine (`crawler`)
- [ ] **Task 3: Token-Bucket Rate Limiter & Async GCP Client**
  - Implement `mindthespot/crawler/rate_limiter.py` (concurrency semaphore + token bucket $\le 15\text{ req/s}$ with jittered backoff).
  - Implement `mindthespot/crawler/client.py` (HTTP/2 async client for GCP `advice.capacityHistory`).
  - Implement `mindthespot/crawler/models.py` (API request/response Pydantic models).
  - *Verify:* `pytest tests/test_crawler.py` passes with mocked GCP API fixtures.
- [ ] **Task 4: Crawler Orchestrator & Dry-Run CLI**
  - Implement `mindthespot/crawler/extractor.py` (iterates catalog and custom watchlist targets, manages batch concurrency, collects snapshot records).
  - Add `mindthespot crawl --dry-run` to output JSON summary without BigQuery.
  - *Verify:* Dry-run execution generates structured records for mock targets.

### Checkpoint 2: Crawler Engine Validated
- [ ] Token-bucket rate limiter enforces $\le 15\text{ req/s}$ under simulated high concurrency.
- [ ] Exponential backoff recovers gracefully from mock `429` / `503` errors.

---

### Phase 3: BigQuery Storage & Anomaly Analytics (`storage-analytics`)
- [ ] **Task 5: BigQuery DDL & Partitioned Storage Ingestion**
  - Create `sql/ddl/01_raw_preemption_history.sql` (daily partitioned, clustered by region/zone/machine_type).
  - Create `sql/ddl/02_raw_price_history.sql` (daily partitioned, clustered by region/machine_type).
  - Implement `mindthespot/storage/bigquery_client.py` and `schemas.py` (batch append with partition idempotency).
  - *Verify:* `pytest tests/test_bigquery_storage.py` passes.
- [ ] **Task 6: Regime Shift & Pivot SQL Views + Python Analytics Engine**
  - Create `sql/views/01_v_regime_shifts.sql` (rolling 7d vs 23d baseline Z-score, price step delta).
  - Create `sql/views/02_v_pivot_recommendations.sql` (sibling zone + equivalent family matching).
  - Implement `mindthespot/analytics/statistical.py` and `pivot_rules.py` (Python algorithms for offline analysis and testing).
  - *Verify:* `pytest tests/test_analytics.py` passes against synthetic time-series data.

### Checkpoint 3: Analytics & Storage Validated
- [ ] Statistical tests verify that $Z \ge 2.5$ triggers `CRITICAL` alert with preemption floor filter.
- [ ] Pivot engine accurately matches fallback sibling zones and equivalent compute families.

---

### Phase 4: Backend API Layer (`api`)
- [ ] **Task 7: FastAPI Service & Query Caching**
  - Implement `mindthespot/api/service.py` (BigQuery client execution with 15-minute `TTLCache`).
  - Implement REST routes:
    - `GET /api/v1/anomalies`
    - `GET /api/v1/pools`
    - `GET /api/v1/pools/{region}/{zone}/{machine_type}/history`
    - `GET /api/v1/pivots/{region}/{zone}/{machine_type}`
    - `GET /api/v1/watchlist`
  - Implement `mindthespot/api/main.py` (FastAPI app, CORS, OpenAPI schemas).
  - *Verify:* `pytest tests/test_api.py` passes with FastAPI `TestClient`.

### Checkpoint 4: API Layer Validated
- [ ] All REST endpoints return expected schemas and headers.
- [ ] TTL cache prevents duplicate queries within 15 minutes.

---

### Phase 5: Modern Frontend Dashboard (`web-ui`)
- [ ] **Task 8: Frontend Scaffolding, Theme & API Client**
  - Initialize `frontend/` with Vite, React 18, TypeScript, Tailwind CSS, Lucide React.
  - Setup core UI components (shadcn/ui style Card, Badge, Button, Tabs, Dialog, Tooltip).
  - Configure TanStack Query client and typed API client in `frontend/src/lib/api.ts`.
  - *Verify:* `npm run build` succeeds in `frontend/`.
- [ ] **Task 9: Situation Room & Anomaly Cards**
  - Implement `SituationRoom.tsx` (feed of active regime shifts sorted by Z-score severity).
  - Implement `AnomalyCard.tsx` (severity badge, preemption delta pill, hourly price, pivot CTA).
  - *Verify:* Component renders accurately with mock anomaly payloads.
- [ ] **Task 10: Interactive Explorer, Charts & Pivot Comparison**
  - Implement `PoolExplorer.tsx` (Region / Family / Zone filter bar and pool grid).
  - Implement `PreemptionChart.tsx` (Recharts 30-day preemption curves with threshold reference lines).
  - Implement `PriceTimeline.tsx` (Recharts step-function 1-year price intervals).
  - Implement `PivotModal.tsx` (side-by-side fallback comparison with sibling zones and cross-family alternatives).
  - Implement `WatchlistToggle.tsx` (filter between custom watchlist and global defaults).
  - *Verify:* Charts render smoothly and respond to region/machine type selection.

### Checkpoint 5: Frontend Validated
- [ ] React SPA builds without errors or warnings (`npm run build`).
- [ ] Situation Room, Explorer, and Pivot modal work seamlessly with live or mock API data.

---

### Phase 6: Unified CLI, Production Serving & Packaging (`cli`)
- [ ] **Task 11: Unified CLI & Single-Container Production Serving**
  - Implement `mindthespot/cli.py` (Typer CLI: `crawl`, `serve`, `analyze`).
  - Integrate static SPA mounting into `mindthespot/api/main.py` to serve `frontend/dist` on `/`.
  - Create `Dockerfile` for Cloud Run container deployment.
  - *Verify:* `mindthespot serve --port 8080` serves both frontend on `/` and API on `/api/v1/*`.

### Final Checkpoint: End-to-End System Complete
- [ ] Full automated test suite passes (`pytest -v`).
- [ ] Frontend production build verified (`npm run build`).
- [ ] CLI commands functional end-to-end.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **GCP API Rate Limiting (429s)** | High | Client-side Token-Bucket limiter enforcing $\le 15\text{ req/s}$ with jittered exponential backoff. |
| **BigQuery Query Scan Costs** | Medium | In-memory 15-minute `TTLCache` on FastAPI layer; partitioned queries by `snapshot_date`. |
| **Noisy Preemption in Low-Volume Zones** | Medium | Dual-gate threshold: Z-score $\ge 2.5$ AND absolute 7-day rate floor $\ge 20\%$ to reject micro-noise. |
| **Missing Price or Preemption in New Regions** | Low | Graceful Pydantic parsing with nullable fields and default zero/empty fallbacks. |
