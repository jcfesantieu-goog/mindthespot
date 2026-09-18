# MindTheSpot — Antigravity Agent Guidelines & Rules

## 1. Project Context & Environment
- **Lead Engineer**: JC (`jcfesantieu`) — Girondins de Bordeaux supporter ⚽
- **GCP Project**: `jcf-mindthespot` (Project Number: `903096587182`)
- **Default Region**: `europe-west4` (Cloud Run, BigQuery, Artifact Registry)
- **Production URL**: `https://spot-8-232-252-55.sslip.io/` (Behind Cloud IAP)
- **Datasets**:
  - Raw Telemetry & Pricing: `mindthespot_raw` (`price_history`, `preemption_history`, `on_demand_pricing`)
  - Analytical Views: `mindthespot_analytics` (`v_regime_shifts`, `v_pivot_recommendations`)

---

## 2. Core Engineering Principles

### A. Root-Cause Debugging & No Silent Fallbacks
- **Zero Silent Mock Fallbacks**: Never allow production services or API methods to silently fall back to synthetic/mock data when BigQuery or external APIs fail. 
- Always log full exception tracebacks (`logger.error("...", exc, exc_info=True)`).
- When investigating anomalies (e.g. unexpected shift counts or flat price lines), inspect the actual database partitions and Cloud Logging (`gcloud logging read`) first before assuming UI or caching bugs.

### B. Terraform & BigQuery State Parity
- **Never create or mutate BigQuery tables/views out-of-band without Terraform state parity**:
  - If a table or view is populated via a seeder script or DDL, immediately ensure it is managed in `terraform/bigquery.tf` and imported into remote state (`gs://jcf-mindthespot-tfstate`) to prevent `409 Already Exists` failures in the GitOps pipeline.
- Analytical views in `sql/views/templates/*.sql.tpl` must always stay synchronized with rendered SQL files in `sql/views/*.sql` and deployed BigQuery views.

### C. GCP Capacity History Telemetry Rules
- **Interval Expansion**: Google Compute Engine Capacity History API compresses identical contiguous daily rates into `[startTime, endTime)` intervals. Always expand intervals into individual calendar days (`DailyPreemptionRate`) across $[startTime, endTime)$.
- **Ingestion Idempotency**: Prior to crawling a date snapshot, invoke `purge_snapshot(snapshot_date, region)` to ensure re-runs or test runs do not duplicate data.
- **Analytical Deduplication**: All SQL views and in-memory pre-warm queries MUST include window-based deduplication (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY crawled_at DESC) = 1`).

---

## 3. Pre-Flight Verification & Quality Gates

Before declaring any task complete or pushing commits to `main`:

1. **Python Quality**:
   ```bash
   ./.venv/bin/ruff check .
   ./.venv/bin/pytest tests/
   ```
2. **Frontend Production Build**:
   ```bash
   npm --prefix frontend run build
   ```
3. **Git Hygiene**:
   - Use Conventional Commits (`feat(...)`, `fix(...)`, `docs(...)`, `refactor(...)`, `chore(...)`).
   - Push to `origin/main` with `BypassSandbox: true` and monitor the GitHub Actions GitOps workflow (`gh run list` / `gh run watch`) to confirm deployment success.

---

## 4. Living Documentation Protocol
Whenever modifying architecture, schemas, or resolving incidents:
- **`SPEC.md`**: Update table schemas, API schemas, mathematical definitions, and architectural diagrams.
- **`issue.md`**: Log production incidents with timeline, root-cause analysis, 5-pillar fix breakdown, and test verification proof.
