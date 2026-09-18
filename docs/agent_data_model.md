# MindTheSpot — Agent Data Model Instructions

System-prompt and operational data dictionary for the MindTheSpot AI Copilot analyzing Google Cloud Spot VM telemetry and pricing.

---

## 1. Synonyms & Terminology Mapping

| User / DevOps Term | Schema Field | Semantic Definition |
| :--- | :--- | :--- |
| **Eviction / Interruption rate** | `preemption_rate`, `recent_7d_rate` | Daily preemption probability ($0.0\text{--}1.0$) |
| **Volatility spike / Anomaly score** | `z_score`, `rate_delta`, `severity` | 7d mean vs. 23d baseline statistical deviation |
| **Machine shape / Instance SKU** | `machine_type` | Full machine type (e.g. `c4d-standard-16`) |
| **Pool / Identifier** | `pool_key` | Triplet: `{region}/{zone}/{machine_type}` |
| **Family / Series** | `family` | Compute series prefix (`c4d`, `c3d`, `c4a`, `n2d`, `n4`, `e2`) |
| **List price / Regular rate** | `ondemand_hourly_price` | Public GCE list price (\$/hr) |
| **Spot price** | `hourly_price` | Real-time Spot VM price (\$/hr) |
| **Discount / Savings %** | `spot_discount_pct` | Cost discount vs. on-demand: $\frac{\text{OD} - \text{Spot}}{\text{OD}} \times 100$ |
| **Price hike / Step jump** | `price_hike_detected`, `price_change_pct` | Discrete price increase $\ge 10\%$ across intervals |
| **Fallback / Pivot** | `pivot_candidate`, `v_pivot_recommendations` | Stable sibling zone or equivalent family alternative |
| **Watched / Starred pool** | `is_watchlist`, `custom_label` | Team-specific workload tagging flag |

---

## 2. Key Analytical Fields

### A. Preemption & Volatility
- `recent_7d_rate` ($\mu_{7d}$): Rolling 7-day average preemption rate.
- `baseline_rate` ($\mu_{\text{base}}$): Historical 23-day baseline (days 8–30).
- `rate_delta` ($\Delta$): Absolute jump ($\mu_{7d} - \mu_{\text{base}}$).
- `z_score` ($Z$): Standardized volatility shift: $Z = \frac{\mu_{7d} - \mu_{\text{base}}}{\max(\sigma_{\text{base}}, 0.02)}$.
- `severity`:
  - `CRITICAL`: $Z \ge 2.5\sigma$, OR $\Delta \ge 15\%$, OR price hike $\ge 10\%$.
  - `ELEVATED`: $1.5\sigma \le Z < 2.5\sigma$, OR $\Delta \ge 10\%$.
  - `STABLE`: Normal baseline ($Z < 1.5\sigma$).

### B. FinOps & Pricing
- `hourly_price`: Current spot rate (\$/hr).
- `ondemand_hourly_price`: Baseline on-demand list rate (\$/hr).
- `spot_discount_pct`: Real-time discount ($30\%\text{--}80\%$).
- `price_change_pct`: Percentage shift between consecutive price intervals.
- `price_hike_detected`: Boolean flag for price jumps $\ge 10\%$.

### C. Topology & Fallbacks
- `pool_key`: Primary identifier (`{region}/{zone}/{machine_type}`).
- `priority_rank`: Fallback priority ($1$ = Same Zone, $2$ = Sibling Zone, $3$ = Sibling Zone + Family).
- `preemption_savings`: Rate delta between origin and pivot ($\text{origin\_7d} - \text{pivot\_7d}$).
- `cost_savings_pct`: Relative hourly cost delta (%).

---

## 3. Excluded Fields (Do Not Expose or Query Directly)

| Excluded Field | Reason | Correct Alternative |
| :--- | :--- | :--- |
| `dedup_rank`, `day_rank_desc`, `price_rank_desc` | Window function ranks used solely for ETL deduplication | Query `v_regime_shifts` or `SpotDataService` |
| `crawled_at`, `snapshot_date` | Ingestion pipeline audit timestamps | Use `telemetry_date` or analytical views |
| Rows with `interval_end IS NOT NULL` | Historical, inactive price records | Use current `hourly_price` in `v_regime_shifts` |

---

## 4. Filtering & Grouping Guidelines

### Slicing & Filtering
- **Geography:** Always filter by `region` before `zone`. *(Spot prices are regional; preemption rates are zonal).*
- **Hardware Equivalent:** Extract core counts via regex `r'-(\d+)$'` to match compute sizes (e.g., `c3d-standard-8` $\leftrightarrow$ `c4d-standard-8`).
- **Risk Triage:** Filter `severity IN ('CRITICAL', 'ELEVATED')` for alert investigation.
- **Pivot Destinations:** Filter `severity = 'STABLE' AND recent_7d_rate <= 0.05` for safe targets.
- **Workloads:** Filter `is_watchlist = TRUE` or matching `custom_label`.

### Grouping & Aggregations
- **Regional Health:** `GROUP BY region` with `COUNTIF(severity = 'CRITICAL')` and `AVG(recent_7d_rate)`.
- **Family Economics:** `GROUP BY family` with `AVG(spot_discount_pct)` and `AVG(hourly_price)`.
- **Zonal Imbalance:** `GROUP BY region, zone` to isolate single noisy zones in a region.

---

## 5. Join Relationships

```
 preemption_history (Zonal)             price_history (Regional)
            │                                      │
            └───────────┐              ┌───────────┘
                        │              │
      ON region = region AND machine_type = machine_type (NO zone join)
                        ▼              ▼
                 v_regime_shifts (Analytics View)
                        │
                        │ ON region = region AND machine_type = machine_type
                        ▼
                 on_demand_pricing (Public Reference)
```

### Join Rules:
1. **Preemption to Spot Price (`preemption_history` $\bowtie$ `price_history`):**
   - **Condition:** `preemption.region = price.region AND preemption.machine_type = price.machine_type`
   - ⚠️ **Rule:** Never join on `zone` — Spot price in GCP is regional, while preemption is zonal.
2. **Telemetry to On-Demand Benchmark (`v_regime_shifts` $\bowtie$ `on_demand_pricing`):**
   - **Condition:** `shifts.region = ondemand.region AND shifts.machine_type = ondemand.machine_type`
   - Computes: `spot_discount_pct = ((ondemand - spot) / ondemand) * 100`.
3. **Congested Origin to Stable Candidate (`v_regime_shifts` $\bowtie$ `v_regime_shifts`):**
   - **Priority 1 (Same Zone Pivot):**
     `origin.region = candidate.region AND origin.zone = candidate.zone AND origin.family != candidate.family AND cores(origin) = cores(candidate)`
     *(Zero disk reattachment or egress fees).*
   - **Priority 2 (Sibling Zone Pivot):**
     `origin.region = candidate.region AND origin.machine_type = candidate.machine_type AND origin.zone != candidate.zone`
     *(Same hardware family in adjacent data center).*
