# MindTheSpot — Architecture & AI Operational Guidelines

## 1. Project Overview & Philosophy
- **Lead Engineer**: JC (`jcfesantieu`) — Girondins de Bordeaux supporter ⚽
- **Objective**: Internal FinOps & DevOps early-warning intelligence platform analyzing Google Cloud Spot VM preemption and pricing telemetry.
- **Core Goals**:
  1. Detect statistical volatility spikes ($Z \ge 2.5\sigma$) and discrete price hikes ($\ge 10\%$).
  2. Provide automated fallback recommendations (stable sibling zones & equivalent machine families).
  3. Display real-time spot vs. on-demand discounts ($30\%\text{--}80\%$) backed by public pricing matrices.
  4. Serve private enterprise traffic securely via Cloud IAP in Google Cloud Argolis.
- **Tech Stack**:
  - **Backend**: Python 3.12+, FastAPI, Uvicorn, Pydantic v2, `httpx` (HTTP/2 connection pooling).
  - **Data**: BigQuery (`mindthespot_raw` partitioned tables, `mindthespot_analytics` SQL views).
  - **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts.
  - **Infra/Edge**: Cloud Run, Cloud Run Jobs, Global External ALB (`EXTERNAL_MANAGED`), Serverless NEG, Cloud IAP, Google-managed SSL (`sslip.io`), Terraform.

---

## 2. Architecture & Directory Structure

```text
mindthespot/
├── frontend/                   # React 18 + Vite + Tailwind UI (bundled to dist/)
│   ├── src/components/         # Situation Room, Pool Explorer, Pivot Drawer, Modals
│   └── src/App.tsx             # Root dashboard & Cloud IAP user identity resolution
├── mindthespot/                # Core Python Package
│   ├── api/                    # FastAPI server (app.py, auth.py, schemas.py, service.py)
│   ├── catalog/                # Catalog definitions (builder.py, models.py, watchlist.py)
│   ├── crawler/                # GCE API ingestion (client.py, extractor.py, rate_limiter.py)
│   ├── storage/                # BigQuery client (bigquery_client.py, pricing_seeder.py)
│   └── cli.py                  # Typer CLI entrypoint (crawl, serve, api, seed-pricing)
├── sql/                        # BigQuery schemas (ddl/) and views (views/templates/, views/*.sql)
├── terraform/                  # Declarative IaC (cloud_run.tf, load_balancer.tf, bigquery.tf, iam.tf)
├── GEMINI.md                   # AI operational guidelines & architectural context
└── SPEC.md                     # Mathematical models & formal specifications
```

- **Serving Pipeline**: Cloud Run mounts the compiled React bundle at `/` and serves REST endpoints under `/api/v1/*`.
- **Ingestion Pipeline**: Scheduled Cloud Run Job crawls 43 regions (6,240 pools) weekly, streaming directly to BigQuery raw tables.

---

## 3. Core Features & Workflow Logic

1. **Statistical Regime Shift Engine (`v_regime_shifts`)**:
   - Recent mean $\mu_{7d}$ (days 1–7) vs. baseline mean $\mu_{\text{base}}$ & stddev $\sigma_{\text{base}}$ (days 8–30):
     $$Z = \frac{\mu_{7d} - \mu_{\text{base}}}{\max(\sigma_{\text{base}}, 0.02)}$$
   - Classifications: `CRITICAL` ($Z \ge 2.5\sigma$ or $\Delta \ge 15\%$ or price hike $\ge 10\%$), `ELEVATED` ($1.5\sigma \le Z < 2.5\sigma$), `STABLE`.
2. **Automated Pivot Recommendations (`v_pivot_recommendations`)**:
   - Matches congested pools to stable sibling zones (same machine type, rate $\le 5\%$, $Z < 1.0$) and hardware-equivalent families (`c3d` $\leftrightarrow$ `c4d` $\leftrightarrow$ `c4a`/Axion $\leftrightarrow$ `n2d`).
3. **On-Demand vs. Spot Discounting**:
   - Stored in `mindthespot_raw.on_demand_pricing`.
   - Real-time discount: $\text{Discount \%} = \frac{\text{OnDemand} - \text{Spot}}{\text{OnDemand}} \times 100$.
4. **Hybrid In-Memory Pre-Warming (ADR 002)**:
   - On boot, `SpotDataService` loads all pools and curves into RAM dictionaries ($\approx 15\text{ MB}$).
   - API endpoints serve requests in $< 5\text{ ms}$ with zero BigQuery slot usage. Post-crawl refresh triggered via `POST /api/v1/cache/refresh`.

---

## 4. Technical Standards, Conventions & Constraints

### ⚠️ Strict Anti-Patterns & Hard Rules
1. **Zero Silent Fallbacks to Synthetic Mocks**:
   - Production API services must NEVER fall back to synthetic data upon query failure. Always log full tracebacks (`logger.error("...", exc, exc_info=True)`).
2. **Terraform & BigQuery State Parity**:
   - Never create or mutate BigQuery tables out-of-band without importing into Terraform (`terraform import`) and updating `terraform/bigquery.tf`. Prevents `409 Already Exists` CI/CD failures.
3. **Calendar Day Interval Expansion (GCP Capacity History API)**:
   - GCP compresses identical contiguous daily rates into $[startTime, endTime)$. The crawler must always expand these into discrete daily points (`DailyPreemptionRate`) to prevent false $9.6\sigma$ alerts.
4. **Idempotency & Deduplication**:
   - Crawler must invoke `purge_snapshot(snapshot_date, region)` before writing.
   - All SQL views and API queries must apply window deduplication (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY crawled_at DESC) = 1`).
5. **Bounded Concurrency in Crawlers**:
   - Never spawn unbounded `asyncio.gather` tasks. Use a shared `httpx.AsyncClient`, token cache, and 15-worker queue (`asyncio.Queue`) with regional streaming to stay $< 120\text{ MB}$ RAM.
6. **Argolis Edge Security & IAM**:
   - Cloud Run ingress is restricted to `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`.
   - Grant `roles/run.invoker` to `serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com`.
   - Cloud Run `custom_audiences` must include both the public `sslip.io` domain and `iap_client_id`.

---

## 5. Development & Operational Guidelines

### Local Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
npm --prefix frontend install
```

### Pre-Flight Verification Gates (Mandatory Before Push)
```bash
./.venv/bin/ruff check .
./.venv/bin/pytest tests/
npm --prefix frontend run build
```

### Key CLI Commands
```bash
# Run backend dev server (port 8000)
./.venv/bin/python -m mindthespot.cli api --port 8000 --reload

# Run frontend dev server (port 5173, proxies /api to :8000)
cd frontend && npm run dev

# Run production unified server (port 8080)
./.venv/bin/python -m mindthespot.cli serve --port 8080

# Seed on-demand pricing matrix
./.venv/bin/python -m mindthespot.cli seed-pricing --project jcf-mindthespot --dataset mindthespot_raw
```

### Environment Variables
| Variable | Default / Example | Purpose |
| :--- | :--- | :--- |
| `GCP_PROJECT_ID` | `jcf-mindthespot` | Target Google Cloud Project |
| `BIGQUERY_DATASET_RAW` | `mindthespot_raw` | Raw telemetry & pricing dataset |
| `BIGQUERY_DATASET_ANALYTICS` | `mindthespot_analytics` | Analytical views dataset |
| `SYNC_PREWARM` | `true` | Force synchronous BigQuery pre-warm on boot |

### GitOps Deployment
Pushing to `main` triggers `.github/workflows/gitops.yml` (tests $\rightarrow$ container build $\rightarrow$ `terraform apply`).
Monitor runs: `gh run list --limit 1` and `gh run watch <run_id>`.
