# Tasks: MindTheSpot

## Phase 1: Foundations & Core Configuration (`core-config`)

- [x] Task 1: Project Scaffolding & Tooling Setup
  - **Acceptance:** `pyproject.toml` created with all dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `google-cloud-bigquery`, `cachetools`, `typer`, `pytest`, `ruff`), package installable in editable mode, ruff linter configured.
  - **Verify:** `uv pip install -e ".[dev]"` succeeds and `ruff check .` passes without errors.
  - **Files:** `pyproject.toml`, `README.md`, `.gitignore`, `mindthespot/__init__.py`

- [x] Task 2: Catalog & Custom Watchlist Models & Loaders
  - **Acceptance:** Pydantic v2 models define `CatalogConfig`, `WatchlistConfig`, and `InstancePoolTarget`. Loader reads and merges default catalog YAML with custom watchlist YAML with validation.
  - **Verify:** `pytest tests/test_config.py` passes with 100% assertions met.
  - **Files:** `mindthespot/config/models.py`, `mindthespot/config/loader.py`, `config/default_catalog.yaml`, `config/watchlist.example.yaml`, `tests/test_config.py`

### Checkpoint 1: Foundations Validated
- [x] All configuration unit tests pass
- [x] Catalog and custom watchlist YAMLs parse and validate cleanly

---

## Phase 2: Ingestion & Crawler Engine (`crawler`)

- [x] Task 3: Token-Bucket Rate Limiter & Async GCP Client
  - **Acceptance:** Async token bucket enforces $\le 15\text{ req/s}$ with concurrency semaphore. Async HTTP/2 client calls `advice.capacityHistory` for zonal preemption and regional price with exponential backoff on 429/503.
  - **Verify:** `pytest tests/test_crawler.py` passes using mock HTTP responses.
  - **Files:** `mindthespot/crawler/rate_limiter.py`, `mindthespot/crawler/client.py`, `mindthespot/crawler/models.py`, `tests/test_crawler.py`, `tests/conftest.py`

- [x] Task 4: Crawler Orchestrator & Dry-Run CLI
  - **Acceptance:** Extractor loops over configured catalog and custom watchlist targets, dispatches requests under the rate limiter, and aggregates preemption and price records. CLI dry-run outputs summary JSON.
  - **Verify:** `mindthespot crawl --dry-run` executes without error and displays aggregated crawl statistics.
  - **Files:** `mindthespot/crawler/extractor.py`, `mindthespot/cli.py`, `tests/test_crawler.py`

### Checkpoint 2: Crawler Engine Validated
- [x] Concurrency and rate limiting verified under simulated load
- [x] Dry-run crawl produces structured records for targets

---

## Phase 3: BigQuery Storage & Anomaly Analytics (`storage-analytics`)

- [x] Task 5: BigQuery DDL & Partitioned Storage Ingestion
  - **Acceptance:** BigQuery DDL files defined for `preemption_history` and `price_history` (partitioned by `snapshot_date`, clustered by region/zone/machine_type). Client inserts batch rows idempotently without corrupting historical snapshots.
  - **Verify:** `pytest tests/test_bigquery_storage.py` passes with mock BigQuery client.
  - **Files:** `sql/ddl/01_raw_preemption_history.sql`, `sql/ddl/02_raw_price_history.sql`, `mindthespot/storage/bigquery_client.py`, `mindthespot/storage/schemas.py`, `tests/test_bigquery_storage.py`

- [x] Task 6: Regime Shift & Pivot SQL Views + Python Analytics Engine
  - **Acceptance:** SQL views define rolling 7d vs 23d baseline Z-score and price step detection, plus fallback pivot joins. Python analytical engine mirrors logic for offline analysis and fast unit testing.
  - **Verify:** `pytest tests/test_analytics.py` passes against synthetic time-series data.
  - **Files:** `sql/views/01_v_regime_shifts.sql`, `sql/views/02_v_pivot_recommendations.sql`, `mindthespot/analytics/statistical.py`, `mindthespot/analytics/pivot_rules.py`, `tests/test_analytics.py`

### Checkpoint 3: Analytical Engine Validated
- [x] Z-score and price hike detection formulas verified with noise floor safeguards
- [x] Sibling zone and family fallback pivots rank recommendations accurately

---

## Phase 4: Backend API Layer (`api`)

- [x] Task 7: FastAPI Service & Query Caching
  - **Acceptance:** FastAPI app exposes `/api/v1/anomalies`, `/api/v1/pools`, `/api/v1/pools/{r}/{z}/{m}/history`, `/api/v1/pivots/{r}/{z}/{m}`, and `/api/v1/watchlist`. Implements 15-minute in-memory `TTLCache`.
  - **Verify:** `pytest tests/test_api.py` passes testing all endpoints with status 200 and schema validation.
  - **Files:** `mindthespot/api/app.py`, `mindthespot/api/routes.py`, `mindthespot/api/schemas.py`, `mindthespot/api/cache.py`, `tests/test_api.py`

- [x] Task 8: Static File Serving & Backend Verification
  - **Acceptance:** FastAPI mounts `/assets` and serves `index.html` for single-page React client routing fallback. Healthcheck `/api/health` reports status `ok`.
  - **Verify:** `curl http://localhost:8000/api/health` returns `{"status": "ok"}`.
  - **Files:** `mindthespot/api/app.py`, `tests/test_api.py`

### Checkpoint 4: Backend API Verified
- [x] All 5 core REST API routes respond within specification
- [x] 15-minute query caching prevents duplicate data computation

---

## Phase 5: Modern Frontend Dashboard (`web-ui`)

- [x] Task 8: Frontend Scaffolding, Theme & API Client
  - **Acceptance:** React 18 + Vite + TypeScript + Tailwind CSS project initialized with shadcn/ui components (Card, Badge, Button, Tabs, Dialog, Tooltip), TanStack Query, and typed API fetch client.
  - **Verify:** `npm run build` succeeds inside `frontend/`.
  - **Files:** `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.ts`, `frontend/src/App.tsx`, `frontend/src/lib/api.ts`

- [x] Task 9: Situation Room & Anomaly Cards
  - **Acceptance:** Feed of active regime shifts sorted by Z-score severity. Anomaly cards display machine type, zone, Z-score badge, preemption delta pill, hourly price, and quick pivot CTA.
  - **Verify:** Renders correctly in browser with responsive layout.
  - **Files:** `frontend/src/components/SituationRoom.tsx`, `frontend/src/components/AnomalyCard.tsx`

- [x] Task 10: Interactive Explorer, Charts & Pivot Comparison
  - **Acceptance:** Region/zone/family selectors, 30-day preemption curves with threshold reference lines, step-function price timeline, side-by-side pivot comparison drawer, and watchlist toggle.
  - **Verify:** Interactive charts render cleanly without console warnings or layout shifts.
  - **Files:** `frontend/src/components/PoolExplorer.tsx`, `frontend/src/components/PreemptionChart.tsx`, `frontend/src/components/PriceTimeline.tsx`, `frontend/src/components/PivotModal.tsx`, `frontend/src/components/WatchlistToggle.tsx`

### Checkpoint 5: Frontend Validated
- [x] Frontend builds cleanly with zero TypeScript or bundler errors (`npm run build`)
- [x] Full UI workflow verified (Situation Room $\rightarrow$ Explorer $\rightarrow$ Pivot comparison)

---

## Phase 6: Unified CLI, Production Serving & Packaging (`cli`)

- [x] Task 11: Unified CLI & Single-Container Production Serving
  - **Acceptance:** Typer CLI commands (`crawl`, `serve`, `anomalies`, `pivots`). FastAPI serves compiled static SPA on `/` and REST API on `/api/v1/*`. Dockerfile packages application for Cloud Run.
  - **Verify:** `pytest tests/test_cli.py` and `npm run build` succeed cleanly.
  - **Files:** `mindthespot/cli.py`, `mindthespot/api/app.py`, `Dockerfile`, `tests/test_cli.py`

### Final Checkpoint: End-to-End System Complete
- [x] Full test suite passes (`pytest -v`, 36 tests passing)
- [x] Production frontend build verified (`npm run build`)
- [x] Unified server operational on port 8080 with dual API and SPA static serving

---

## Phase 7: Terraform Infrastructure as Code & GitOps Workflow (`iac-gitops`)

- [x] Task 12: Terraform GCP Infrastructure Modules
  - **Acceptance:** Full Terraform configurations for Google APIs, Artifact Registry, BigQuery partitioned tables and analytical views, Cloud Run Service (App), Cloud Run Job (Crawler), and Cloud Scheduler cron.
  - **Verify:** `terraform fmt -check` passes.
  - **Files:** `terraform/versions.tf`, `terraform/variables.tf`, `terraform/apis.tf`, `terraform/artifact_registry.tf`, `terraform/bigquery.tf`, `terraform/cloud_run.tf`, `terraform/cloud_scheduler.tf`, `terraform/outputs.tf`, `terraform/terraform.tfvars.example`

- [x] Task 13: Workload Identity Federation & Least Privilege IAM
  - **Acceptance:** Dedicated Service Accounts (`mindthespot-crawler`, `mindthespot-app`, `mindthespot-scheduler`, `mindthespot-cicd`) with PoLP roles, and GitHub Actions OIDC Workload Identity Pool and Provider.
  - **Verify:** IAM bindings and attribute conditions match GitHub repo specification without static keys.
  - **Files:** `terraform/iam.tf`

- [x] Task 14: GitHub Actions CI/CD & GitOps Pipelines
  - **Acceptance:** `.github/workflows/ci.yml` runs test gates (Python lint/tests + React build + Terraform fmt), and `.github/workflows/gitops.yml` builds/pushes container to Artifact Registry and updates Cloud Run.
  - **Verify:** Workflows pass YAML linting and validation.
  - **Files:** `.github/workflows/ci.yml`, `.github/workflows/gitops.yml`

### Checkpoint 7: Terraform & GitOps Validated
- [x] Terraform files formatted and validated
- [x] Workflows and IaC committed and pushed to GitHub




---

## Phase 8: Enterprise Security, Cloud IAP & Custom Domain (`iap-edge`)

- [x] Task 15: Global External HTTPS Load Balancer with Serverless NEG
  - **Acceptance:** Provision global Anycast IPv4 address (`8.232.252.55`), Serverless NEG in `europe-west4`, backend service targeting Cloud Run, and URL map with HTTP to HTTPS port 80 -> 443 301 redirection.
  - **Verify:** Load Balancer routes traffic to Cloud Run service without direct internet exposure.
  - **Files:** `terraform/load_balancer.tf`, `terraform/outputs.tf`

- [x] Task 16: Dynamic DNS with sslip.io & Google-Managed SSL Certificate
  - **Acceptance:** Automate FQDN computation `spot-${replace(local.lb_ip, ".", "-")}.sslip.io` (`spot-8-232-252-55.sslip.io`) and attach `google_compute_managed_ssl_certificate`.
  - **Verify:** Browser connection establishes secure TLS connection with Google Trust Services valid certificate.
  - **Files:** `terraform/load_balancer.tf`

- [x] Task 17: Cloud Identity-Aware Proxy (IAP) & DRS Compliance
  - **Acceptance:** Configure IAP on the Load Balancer backend service with OAuth 2.0 Web Client. Enforce `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` on Cloud Run. Bind `roles/run.invoker` to IAP Service Agent (`serviceAccount:service-903096587182@gcp-sa-iap.iam.gserviceaccount.com`). Bind `roles/iap.httpsResourceAccessor` to authorized enterprise identity (`domain:jcfesantieu.altostrat.com`, `user:sre@jcfesantieu.altostrat.com`). Add `custom_audiences` to Cloud Run.
  - **Verify:** Direct `*.run.app` access returns 403. Access via `https://spot-8-232-252-55.sslip.io/` triggers Google OAuth login and permits authenticated users.
  - **Files:** `terraform/iap.tf`, `terraform/cloud_run.tf`, `docs/adr/001-cloud-iap-load-balancer-sslip.md`

### Checkpoint 8: Production Edge Security Complete
- [x] Zero-Trust access model operational and verified live
- [x] Domain Restricted Sharing organizational constraint fully satisfied
- [x] Cloud Run secured against direct public invocations

---

## Phase 9: Permanent BigQuery Watchlist Storage & Table-Level IAM (`bq-watchlist`)

- [x] Task 18: BigQuery Schema & Terraform Table-Level IAM
  - **Acceptance:** Declare `google_bigquery_table.user_watchlists` in `terraform/bigquery.tf` clustered by `(user_email, region)` with active flag, workload metadata, and thresholds. Attach `google_bigquery_table_iam_member` granting `roles/bigquery.dataEditor` exclusively to `google_service_account.app.email` on `user_watchlists`. Datasets remain read-only (`roles/bigquery.dataViewer`).
  - **Verify:** `terraform validate` and `terraform fmt -check` pass.
  - **Files:** `terraform/bigquery.tf`, `sql/ddl/04_raw_user_watchlists.sql`

- [x] Task 19: BigQuery Watchlist Storage Methods & In-Memory Pre-Warm Hydration
  - **Acceptance:** Implement `BigQueryClient.fetch_user_watchlists(user_email)` and `BigQueryClient.save_user_watchlist_entries(...)`. Update `SpotDataService.warm_cache_from_bigquery()` to hydrate active user watchlists into memory on boot. Update `add_watchlist_entry()`, `toggle_watchlist_pool()`, and `remove_watchlist_target()` to optimistically update in-memory cache and asynchronously write changes to BigQuery.
  - **Verify:** Unit tests pass with mocked BigQuery client in `tests/test_api.py` and `tests/test_bigquery_storage.py`.
  - **Files:** `mindthespot/storage/bigquery_client.py`, `mindthespot/storage/schemas.py`, `mindthespot/api/service.py`, `mindthespot/api/routes.py`, `mindthespot/api/schemas.py`, `tests/test_api.py`

- [x] Task 20: Frontend Multi-Device Watchlist Sync & Hydration
  - **Acceptance:** Implement `watchlistStorage.ts` to manage robust client cache with automatic migration. Wire `App.tsx` and `api.ts` to fetch and sync watchlists directly from backend upon boot and upon mutation, keeping client and BigQuery in sync across browser refreshes and container restarts.
  - **Verify:** `npm run build` succeeds cleanly.
  - **Files:** `frontend/src/lib/watchlistStorage.ts`, `frontend/src/lib/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/WatchlistModal.tsx`

### Checkpoint 9: BigQuery Watchlist Persistence Validated
- [x] Table-level least-privilege IAM verified in Terraform
- [x] Backend retains watchlists across simulated container cold-starts and BigQuery refreshes
- [x] Frontend maintains full state across browser reloads and multi-device sessions
