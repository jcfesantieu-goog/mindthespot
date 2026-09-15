# MindTheSpot 🎯

> **GCP Spot VM Regime Shift Warning & Fallback Pivot Engine**

MindTheSpot is an internal FinOps and DevOps intelligence platform that automatically collects, analyzes, and visualizes Google Cloud Spot VM preemption rates and pricing telemetry.

Instead of passive telemetry, MindTheSpot acts as an **early-warning and decision engine**:
* **Regime Shift Detection:** Benchmarks rolling 7-day preemption metrics against a 30-day baseline to detect statistical volatility spikes ($Z \ge 2.5$) and alerts on discrete price increases ($\ge 10\%$).
* **Automated Pivot Recommendations:** Recommends alternative stable zones (same machine type) or equivalent machine families (e.g. `c3d` $\leftrightarrow$ `c4d` $\leftrightarrow$ `c4a`/Axion $\leftrightarrow$ `n2d`) when an active pool becomes congested.
* **Modern Operational Dashboard:** High-density React + Tailwind CSS + shadcn/ui frontend with interactive Recharts time-series curves.

---

## Quickstart

### 1. Installation
```bash
# Clone the repository
git clone <repo-url>
cd mindthespot

# Set up Python environment
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Running Tests
```bash
pytest -v
ruff check .
```

### 3. Running the Crawler
```bash
# Dry-run crawl with terminal summary
mindthespot crawl --dry-run

# Ingest into BigQuery
mindthespot crawl --output=bigquery --project=<YOUR_GCP_PROJECT> --dataset=mindthespot_raw
```

### 4. Running the Dashboard
```bash
# Production server (serves FastAPI + compiled React frontend on port 8080)
mindthespot serve --port 8080

# Or run Vite frontend dev server
cd frontend && npm install && npm run dev
```

---

## Architecture & Specifications

For comprehensive details on system design, BigQuery DDL, API contracts, and math rules, see [SPEC.md](docs/spec/SPEC.md).
