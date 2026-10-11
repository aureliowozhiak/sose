# PC6: real Trading Company statecharts + shared physical ledger + recurring restart

**Status:** experimental end-to-end promotion probe for issue #406. Not yet a full promotion guarantee.

## PRD

The same two Trading Company organizations must survive actual worker death while consuming a single authoritative, finite Logistics courier pool. Each organization owns its own PostgreSQL OLTP namespace, writer epoch, correlation, immutable domain events, boundary receipts, certificates, job triggers and independent simulation position. Shared physical reservation truth lives in a separate PostgreSQL namespace. Worker death must not turn a transport ACK into a business certificate, duplicate causal evidence, move an unrelated organization's logical clock or double-book a courier.

The domain path, executed by production domain handlers and reconstructed outbound messages rather than fabricated terminal events, is:

```mermaid
flowchart LR
  W[Warehouse / Dispatch] --> L[Real Logistics statechart]
  L --> O[Real O2C statechart]
  O --> P[Real Cards Payments statechart]
  P --> R[Real Record-to-Report statechart]
```

## TRD

A real, durably seeded customer request initializes stock, Order-to-Cash, Logistics, Cards Payments and Record-to-Report. A test-only abort at the accepted Logistics Command ends synchronous demonstration setup, without certifying Logistics: the recurring scheduler then owns **all subsequent business execution**.

Each `RecoverySchedule` processes a bounded action per logical slot through a real `TradingCustomerRecoveryRunner`; a new PostgreSQL connection is created for each slot. Real domain transitions go through `trading_company_customer._execute_intent` and the ordinary `BusinessEffectService`. The authoritative `IntentResourceCoordinator` checks one physical courier ledger shared between the two organizations and qualifies local effect IDs by operational namespace.

The initial falsification cuts the actual worker via `os._exit(79)` after the real Logistics domain has committed its immutable business-effect certificate and before releasing the physical reservation or checkpointing the recurring slot. Organization B executes a scheduled occurrence while A is dead. A reopens both domain and resource connections and retries its original unfinished occurrence; later slots must reconstruct and complete the real O2C, payment and accounting workflow.

The oracle reads the two reopened operational namespaces and authoritative resource ledger, verifying entity versions, domain events, receipts, immutable messages, causal DAG, settlement binding, complete job checkpoints, simulation position, resource intervals and events. Physical booking IDs are normalized only by removing deployment namespace scope and then sorting. No business IDs, causal edges or logical time may be discarded.

### Durable action accounting beyond physical resources

The first real O2C post-certificate worker-death falsification uncovered a one-slot discrepancy: domain certificates and DAG facts were identical, but the recovered worker consumed an unfinished O2C slot by publishing a later boundary, advancing the downstream chain one tick early. Only Logistics had an authoritative booking-to-trigger link, so completed non-resource business effects were missing from restart work accounting.

`SimulationJobState.active_effect_ids` now records immutable **unmapped** business Command IDs in the job's fenced UoW **before** executing the actual statechart. An interrupted recurrence reconstructs this set, checks the original durable ACK and terminal `BusinessEffectApplied` certificate, and debits already committed effects from that same slot's bounded action budget. If the Command remains pending, it is retried without charging completed work; if both Command and certificate are absent, recovery fails closed. Successfully completed triggers clear the enrollment atomically with the checkpoint. Mapped Logistics effects remain accounted for by the authoritative physical ledger; no synthetic physical reservations are added to O2C, Payments or R2R to hide a scheduler bug.

### Expanded executable OS-kill cuts and causal audit

The combined PostgreSQL falsifier now terminates actual processes in **eight distinct cases**: after Logistics certification and before physical release; after O2C, Cards Payments and R2R certification but before the original recurring checkpoint; and **before** the immutable business-effect certificate for each of Logistics, O2C, Payments and R2R (after the respective real domain statechart already committed its terminal entity/event). The oracle compares each to its own continuous reference across two independent organizations, preserves the entire authoritative courier ledger and all job checkpoint identities, and rejects even a one-slot advancement caused by recovered work.

The required `pc6-real-multidomain.json` bundle uses protocol `pc6-real-multidomain-recurring-v2` with exactly eight named cases, SHA-256 digests, per-organization certificate cardinality, and an aggregate equivalence flag. CI validates every case before publishing the artifact.

**Causal-link boundary:** The legacy Trading Company reference producer retains a real `causation_id` predecessor for the seven inter-domain boundaries but some messages still lack the opt-in `causation_kind="boundary"` discriminator. The test audits all seven exact predecessor identities, correlations, and logical-time ordering, and preserves the typed audit edges that actually exist; **this is not evidence that every legacy message has been migrated to the stronger typed protocol**.

**Required artifact:** `pc6-real-multidomain.json` on PostgreSQL CI. It contains canonical hashes of reference and recovered runs.

## ADR: staged promotion, not a blanket distributed exactly-once claim

This experiment combines previously separate real-domain and physical-ledger proof axes without replacing actual domain handlers with synthetic terminal fixtures. Its first cut is already covered for real Logistics alone in #443/#446, but full continuation through O2C, Cards Payments and R2R under a durable recurring schedule has not yet been certified across two organizations. Once that becomes green, extend the process-kill matrix to claim, atomic ACK+Command, all four mid-statechart transitions and post-certificate/pre-trigger checkpoints, including per-trigger action accounting for *unmapped* effects. Existing #447 proves those cuts against deterministic reference domain transitions, not the real statecharts.

Keep #406 open until the entire cross-domain, cross-organization matrix passes and the remaining PostgreSQL crash/restart, network partition, worker fencing and finite physical-instance tests are independently falsified.
