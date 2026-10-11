# PC6 — Scientific promotion and finite closeout

**Decision record / ADR:** PC6-PROMOTION-2026-10-11  
**Tracked issue:** [#406](https://github.com/brunolnetto/sose/issues/406)  
**Reference experiment:** Trading Company customer demand, real Logistics → O2C → Cards Payments → Record-to-Report statecharts  
**Status:** conditional on the exact-head and post-merge promotion gates described below

## 1. Research question (PRD)

Can a periodically scheduled SOSE composition job, operating in two independent organizational namespaces with an authoritative shared finite physical resource, recover after selected real process, writer, network, and PostgreSQL failures **without changing its observable business/causal state or advancing its own logical clock incorrectly**?

This is an experimentally falsifiable, **bounded** claim about explicitly listed failures. It is not a universal guarantee of distributed exactly-once execution, uninterrupted service during outages, arbitrary interleavings, or all future domains.

### Hypotheses

- **H1 — Durable causal truth:** Full recovery reconstructs the same immutable messages, consumption receipts, domain states/versions/events, business-effect certificates, typed/legacy causal observations, and settlement binding as a continuous reference.
- **H2 — Autonomous organizations:** Organization B can continue a recurring occurrence while A's worker has died or paused; A resumes the **same durable scheduled trigger**, and neither organization requires a fleet-wide writer epoch or clock.
- **H3 — Bounded real work:** A publication, ACK+Command, domain effect, or physical reservation that commits before worker death is accounted against its original recurring slot, exactly as in uninterrupted execution.
- **H4 — Single-writer fencing:** A stale worker cannot mutate authoritative state after a successor acquires a newer epoch; OS death does not strand ownership.
- **H5 — Infrastructure outcome resolution:** A lost TCP connection or stopped/restarted PostgreSQL service around an ACK+Command COMMIT cannot cause the application to invent an outcome. A fresh authoritative connection determines committed receipt+Command vs rollback, followed by equivalence to a compatible continuous reference.

## 2. Operational and technical boundary (TRD)

The real customer workflow is staged using durable customer/request state, then executed through the production `TradingCustomerRecoveryRunner`, `RecoverySchedule`, `BoundaryService`, real domain handlers, `BusinessEffectService`, and PostgreSQL stores; no synthetic terminal domain replacement is permitted.

- Two organizational namespaces, independent logical positions and checkpoints, one capacity-one physical courier pool recorded in a separate authoritative PostgreSQL namespace.
- Workers die using `os._exit(79)` in independent processes for the recurring boundary/statechart experiments. Concurrent stale-writer tests also use real `SIGKILL`.
- Client/server faults use an independent TCP proxy and an actual stop/start of the PostgreSQL service container, on both sides of the ACK+Command COMMIT.
- A re-opened PostgreSQL connection is the authority for the persisted outcome, not a process-local result, transport exception, or mutable test fixture.
- Valid differences: transport lease owner/attempts, connection/session metadata, and deployment-specific namespace qualification of otherwise identical physical booking identities, as normalized explicitly by the comparison oracle.
- Invalid differences: missing/duplicate business events or certificates, changed causal edges, different message/ACK/Command identities, extra resource bookings, altered job `next_tick`, `run_count`, scheduled trigger IDs, or logical time.

### Frozen death/failure matrix

| Evidence | Cases | Conditions |
|---|---:|---|
| Real domain effect/certificate interruption | 8 | Before and after certification for Logistics, O2C, Cards Payments, R2R |
| Real Logistics claim/ACK transaction interruption | 3 | After claim, inside uncommitted ACK+Command, after committed ACK+Command |
| Real downstream transport-boundary interruption | 12 | After publication, after claim, inside ACK+Command, after ACK+Command across O2C, Payments, R2R |
| **Real worker-death certification** | **23** | Two organizations, four real domains, same canonical oracle |
| PostgreSQL service and network interruption | 4 | TCP proxy or actual PostgreSQL restart, before/after COMMIT |
| Concurrent stale-worker and takeover | 2 | SIGKILL successor recovery; live zombie rejected by epoch fencing |

The specialized fencing suite also checks the independent organizational clock and full canonical recovery against a continuous reference.

## 3. Scientific oracle and reproducibility

**Canonical worker-death bundle:** `pc6-real-multidomain.json`, protocol `pc6-real-multidomain-recurring-v3`, **23** required named fault cases. Every case contains the complete `reference_truth` and `recovered_truth`, rather than merely a hash, with independently recomputable SHA-256 over canonical JSON.

**Canonical PostgreSQL infrastructure bundle:** `pc6-infrastructure-canonical.json`, protocol `pc6-postgres-infrastructure-canonical-v1`, **4** required named fault cases. Each case states `ack_outcome` (`rolled_back` or `committed`), publishes both complete truths, and verifies their equality and SHA-256.

**Required observable fields:** causal audit digest and edges, immutable messages, ACK receipts, entities/events/versions, domain certificates and settlement binding, scheduled work, temporal resources, stores, containers, sinks, `SimulationPosition`, `SimulationJobState`, and the full finite physical resource ledger. The oracle does not discard differences in business identity or temporal checkpoints to make failures pass.

Evidence is produced by the mandatory PostgreSQL integration and PostgreSQL infrastructure chaos GitHub Actions jobs, where independent verification rejects missing cases, duplicate case names, incomplete truth, digest mismatches, and non-equivalent results.

Published scientific evidence (see the corresponding workflow and artifact provenance; GitHub retention policy applies):

- [Real worker-death bundle from PR #452](https://github.com/brunolnetto/sose/actions/runs/38146760783/artifacts/11704878806)
- [Full PostgreSQL infrastructure bundle from PR #455](https://github.com/brunolnetto/sose/actions/runs/38146956940/artifacts/11704518692)

To reproduce on an **isolated** PostgreSQL test service, run the explicit PC6 integration file with `SOSE_TEST_POSTGRES_DSN` set. Infrastructure experiments require an actual disposable PostgreSQL container (`SOSE_POSTGRES_CONTAINER_ID`) and access to the isolated TCP proxy test harness. They intentionally stop the database and must **never** target a shared or production PostgreSQL instance.

## 4. Acceptance / promotion gate

PC6 is promoted **only if all five conditions hold**:

1. PR #452 certifies all 23 complete real-worker-death cases and exact-head CI is green.
2. Required historical freezes and Python 3.12/3.13/3.14, PostgreSQL, chaos, coverage, benchmark, and distribution gates are green for the merged `main`.
3. PR #453's stale-writer rejection and takeover tests remain passing on the integrated code.
4. PR #455 certifies four actual PostgreSQL/TCP COMMIT-window failures with independently validated complete canonical snapshots.
5. The decision, hypotheses, protocol, immutable identities, results and limitations are discoverable through this versioned record and the referenced audit bundles.

Green specialized checks are necessary but **not** an exception to the combined post-merge `main` gates. A failure of an already-certified condition invalidates that particular certificate and must be investigated; imagining a new model of failure does not automatically reopen this finite PC6 experiment.

## 5. Decision and limits (ADR)

**Decision:** Close PC6 after the five gates pass. Accept a scoped proof of operational/causal restart equivalence for the enumerated real-statechart, recurring-trigger, stale-writer, TCP interruption, and PostgreSQL restart fault windows. Do not advertise generalized exactly-once semantics, universal fairness, or arbitrary network partition tolerance.

**Out of scope and explicitly not proven by this PC6 artifact:**

- Migrating *all* legacy causal references to typed causal edges; the canonical oracle preserves legacy and typed facts as-is.
- Pools with arbitrary numbers of *physical instances*, repairable failures, preemption, alternative allocation policies, and universal starvation freedom.
- Generalizing the architecture to independent composed MRO or unmodeled external financial processors.
- Arbitrary network partition histories, multi-primary split brain, disk corruption, prolonged unavailable databases, and all possible uncertain COMMIT interleavings.

**Follow-up boundaries:** physical instancing, contention, outages, preemption and fairness belong to **PC7**; MRO as an independent compositional falsifier belongs to **PC8**. Type migration, additional domains, and chaos expansions are standalone hardening work, not retroactive gates on the concluded PC6 scientific claim.

**Rationale:** A reproducible scientific statement must be bounded, disprovable, and publishable. Moving every newly conceivable systems property into PC6 would turn a finite scientific certification into an unending product roadmap.
