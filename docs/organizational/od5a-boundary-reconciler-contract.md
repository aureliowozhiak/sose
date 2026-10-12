# OD-5a durable boundary reconciler — scoped restart and real worker-loss falsification

Tracker: #483. Parents: #477, #480. Previous merged #479 publishes typed physical DomainEvents, and #482 materializes independently versioned and certified downstream observations.

## PRD

A worker's Python process is disposable. A new worker can discover real **already committed** OD-5a execution/coordination events and continue **publish → fenced claim → ACK/Command → observed terminal Entity → independent effect certificate**, one authoritative commit at a time. Every step is restartable from persisted DomainEvents, BoundaryMessages, BoundaryDeliveries, BoundaryConsumptions, Commands, observation Entities and BusinessEffectApplied certificates.

## TRD / runtime scope

- `reconcile_od5a_boundary_once(store, job_id, owner_id, now, lease_duration)` discovers only the requested organization's existing physical DomainEvents. It neither synthesizes physical successes nor advances the SimPy or SQLite physical scheduler.
- Revalidate candidates under UoW using `_physical_event`'s canonical event identity, physical stage-completion witness, model hash, resource class, microsecond duration, causal predecessors and job-clock ordering; publication remains the canonical typed event-derived `BoundaryMessage`.
- A worker advances at most one of **published, claimed, acknowledged, applied, certified** per call. `blocked` signifies unfinished work that cannot advance because of a future event or another worker's live claim; `idle` means all currently known physical events for the organization are certified. A recurrent invoker can poll after a lease expiry or new source event. No in-memory checkpoint is needed for restart.
- Claim is explicitly scoped to an exact `message_id`, registered contract, destination and organizational correlation; live claim owner may ACK, foreign worker must wait for expiry and reclaim with higher epoch. Stale claims never stage Commands.
- Downstream observation and certificate validations are reused, not reimplemented as an unsafe `ACK == effect` shortcut. Proven certificates are reverified on idempotent replay instead of trusted blindly.
- `now` is supplied by the invoker as a timezone-aware time per organization; there is no artificial shared organizational execution clock.
- Integration TDD: five arms × all five after-COMMIT OS death windows, full cross-branch persisted truth vs uninterrupted run, expiration/reclaim fencing with competing workers, and real simultaneous OS processes for two independent organizations with distinct `now` values.

## ADR / limitations and promotion gates

This is a **post-physical-event** boundary reconciler. It does **not** turn the SQLite reference reducer into the normal SimPy production adapter, does not itself durably schedule periodic OS worker invocations, and does not certify PostgreSQL network partition / DB-failure recovery or worker death *inside* every UoW. Those remain #477 production conformance gates. The independent scientific OD-5a execution freeze stays `NOT_ADMITTED`; the 17,920-case DOE is prohibited. No historical Manufacturing/O2C/MRO v1 freeze is modified.
