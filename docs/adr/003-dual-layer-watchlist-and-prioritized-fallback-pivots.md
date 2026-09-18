# ADR 003: Dual-Layer Persistent Watchlist & Prioritized Fallback Pivot Engine Architecture

## Status
**ACCEPTED & IMPLEMENTED** (2026-09-17)

## Context & Problem Statement
MindTheSpot operates as an early-warning and fallback decision engine for FinOps and DevOps practitioners running production workloads on Google Cloud Spot VMs.

Through user feedback and operational testing, two major capability enhancements were identified:

1. **Watchlist Curation & Persistence:**
   - Platform teams monitor specific mission-critical instance pools across multiple regions.
   - Users required the ability to toggle pools into their watchlist with a single click directly from the Pool Explorer table.
   - Watchlist state must persist across browser reloads and sessions while remaining securely segregated per authenticated user email (via Cloud IAP or local development context).
   - The backend engine must also be aware of the user's watchlist so that the Situation Room and alert notifications can prioritize watched pools.

2. **Workload Migration Latency & Cost in Fallback Pivots:**
   - When a spot pool suffers a preemption volatility spike (Regime Shift $Z \ge 2.5\sigma$), workloads must pivot to an alternative stable capacity pool.
   - Previously, pivot recommendations only looked for identical machine types in sibling zones (`ZONE_PIVOT`) or equivalent families in sibling zones (`FAMILY_PIVOT`).
   - Sibling zone migrations introduce **cross-zone network egress latency and data transfer costs**, as well as the operational complexity of detaching and reattaching zonal Persistent Disks (PD).
   - If a comparable instance family is healthy **within the very same availability zone**, pivoting to it avoids cross-zone egress costs and disk detachment entirely.
   - Users also need to evaluate cost differences in **percentage terms** alongside absolute dollars, and directly inspect the 30-day preemption curve of any recommended candidate.

---

## Decision

We designed and implemented two core systems:
1. **A Dual-Layer (Client + Server) Watchlist Persistence Architecture**.
2. **A 3-Tier Prioritized Fallback Pivot Engine** with same-zone preference, relative savings calculations, and 1-click historical inspection.

---

### Architecture 1: Dual-Layer Watchlist Persistence

```
+-------------------------------------------------------------------------+
|                        Frontend Layer (Client)                          |
|  1. User clicks Star icon on Pool Explorer row or Watchlist Target      |
|  2. Optimistic UI update: Star instantly fills in amber                |
|  3. Browser localStorage: mindthespot_watchlist_${email} updated        |
+------------------------------------+------------------------------------+
                                     |
                                     | Asynchronous HTTP Sync
                                     v
+-------------------------------------------------------------------------+
|                        Backend Layer (Cloud Run)                        |
|  POST /api/v1/watchlist/toggle                                          |
|  DELETE /api/v1/watchlist/{region}/{zone}/{machine_type}                |
|                                                                         |
|  - Updates in-memory catalog / BigQuery state                           |
|  - Informs GET /api/v1/anomalies to surface watched pools with priority |
+-------------------------------------------------------------------------+
```

#### Client Storage Mechanics
- Key format: `mindthespot_watchlist_${userContext?.email || "anonymous"}`.
- Value: JSON array of pool keys (e.g. `["europe-west4/europe-west4-a/c4d-standard-8"]`).
- Benefits:
  - **Zero-Latency Interactions:** Star state updates instantaneously with no loading spinners.
  - **Offline Resilience:** Persists across hard reloads, tab closures, and brief network hiccups.
  - **User Isolation:** Automatically scopes saved watchlists to the IAP user email (`userContext.email`).

#### Server Synchronization
- Routes:
  - `POST /api/v1/watchlist`: Adds custom workload watchlist entry.
  - `POST /api/v1/watchlist/toggle`: Accepts `{ region, zone, machine_type, is_watchlist, custom_label }`.
  - `DELETE /api/v1/watchlist?region={region}&name={name}`: Purges an entire named workload watchlist target from memory and persistent store.
  - `DELETE /api/v1/watchlist/{region}/{zone}/{machine_type}`: Removes specific pool target.
- Benefits: Server-side alerting, multi-watchlist filtering, and future webhook integrations can query and manage watched pools independently of browser state.

---

### Architecture 2: 3-Tier Prioritized Fallback Pivot Engine

The pivot matching engine evaluates alternative pools and categorizes them into three prioritized tiers:

```
[ Congested Pool: e.g. c4d-standard-8 in europe-west4-a ]
                          |
                          v
+---------------------------------------------------------------------+
| Tier 1: SAME_ZONE_PIVOT (Priority Rank 1)                           |
| Same Zone (europe-west4-a), Same Core Count (8 vCPUs), Sibling Fam  |
| -> e.g. c3d-standard-8 in europe-west4-a                            |
| Benefit: 0ms Cross-Zone Egress Latency, Zero Persistent Disk Detach |
+---------------------------------------------------------------------+
                          |
                          v
+---------------------------------------------------------------------+
| Tier 2: ZONE_PIVOT (Priority Rank 2)                                |
| Sibling Zone (europe-west4-b), Identical Machine Type               |
| -> e.g. c4d-standard-8 in europe-west4-b                            |
| Benefit: Identical CPU Architecture, Same Performance Profile       |
+---------------------------------------------------------------------+
                          |
                          v
+---------------------------------------------------------------------+
| Tier 3: FAMILY_PIVOT (Priority Rank 3)                              |
| Sibling Zone (europe-west4-b), Same Core Count, Sibling Family      |
| -> e.g. c3d-standard-8 in europe-west4-b                            |
| Benefit: Broadest availability during regional capacity constraints |
+---------------------------------------------------------------------+
```

#### Core Size Extraction Logic
To support `SAME_ZONE_PIVOT` and `FAMILY_PIVOT`, the engine extracts the core count via regular expressions across GCP naming conventions:
- Matches standard shapes: `c4d-standard-8` -> 8 vCPUs.
- Matches highmem/highcpu shapes: `c3d-highmem-16` -> 16 vCPUs.
- Matches custom shapes: `custom-4-16384` -> 4 vCPUs.

Candidates must have identical vCPU counts and equivalent compute tiers (e.g. `c4d` <-> `c3d` <-> `c4a` <-> `n2d`).

#### Candidate Sorting & Cost Savings Calculation
Pivots are deterministically ordered by:
```
Sort Order = (priority_rank ASC, preemption_savings DESC, cost_difference DESC)
```

Cost difference is calculated both as an absolute hourly rate and as a percentage:
```
cost_savings_pct = ((origin_hourly_price - pivot_hourly_price) / origin_hourly_price) * 100
```
Displayed in the UI as: `Save $0.0300/hr (+12.0%)` or `+$0.0100/hr (-4.0%)`.

#### Deep Link Inspection
Each pivot card in `PivotModal.tsx` contains an **Inspect History** button with an `Eye` icon. Clicking it directly invokes `onInspectPool(candidate)`, loading the 30-day preemption curve and 1-year pricing intervals for the candidate pool without needing to leave the workflow.

---

### Architecture 3: Statistical Regime Shifts & Price Step Detection

The Situation Room surfaces statistical anomalies using standardized Z-score formulas with variance flooring:

$$Z = \frac{\mu_{\text{recent 7d}} - \mu_{\text{baseline 23d}}}{\max(\sigma_{\text{baseline}}, 0.02)}$$

- **Critical Regime Shift ($Z \ge 2.5\sigma$):**
  - Tail probability: $p < 0.6\%$.
  - Indicates severe capacity congestion. Eviction risk has structurally spiked far above normal random variance. Immediate pivot required.
- **Elevated Volatility ($Z \ge 1.8\sigma$):**
  - Tail probability: $p < 3.6\%$.
  - Indicates early-warning volatility. Spot pools are beginning to tighten. Platform teams should stage fallback nodepools.
- **Variance Floor ($\max(\sigma_{\text{baseline}}, 0.02)$):**
  - Prevents division-by-zero or wildly inflated $Z$-scores when a pool had $0\%$ preemption historically.
- **Price Step Detection:**
  - **Spot Price Hike ($\ge +5\%$):** Flags discrete spot price increases.
  - **Spot Price Drop ($\le -5\%$):** Flags discrete spot price decreases, highlighting FinOps discount opportunities.
  - Interactive clickable KPI tiles and filter chips in the Situation Room allow filtering instantly by `ALL`, `HIKES_ONLY`, or `DROPS_ONLY`.

---

## Consequences

### Positive
- **Zero Cross-Zone Egress Overheads:** Workloads pivoting to Tier 1 `SAME_ZONE_PIVOT` avoid cross-zone network transfer bills and eliminate the multi-minute downtime associated with detaching and reattaching zonal Persistent Disks.
- **Instant Interactive UI:** Browser `localStorage` provides 0ms response times for watchlist toggles while keeping server-side state in sync.
- **Clear FinOps & Risk Visibility:** Displaying percentage savings alongside dollar amounts clarifies relative economic trade-offs for different instance sizes.
- **Mathematical Transparency:** Interactive methodology explainer demystifies statistical regime shift formulas for DevOps engineers.

### Operational Notes
- For custom/heterogeneous nodepool sizes, if no same-zone sibling family has sufficient capacity, the engine gracefully falls back to Tier 2 and Tier 3 candidates in sibling zones.
