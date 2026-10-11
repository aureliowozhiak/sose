# OD-5a — real OS-process recovery falsifiers (non-confirmatory)

Tracking: #477; prerequisite reference reducer: #474, and immutable physical mechanism pilot: merged #473/#476.

## PRD

Can multiple **real** operating-system worker processes rebuild their independent SQLite connections and progress a fixed OD-5a reference workload without duplicate semantic effects, missing causal predecessors, or global organizational clocks?

## TRD / evidence

- Same-job race: launch two separate `spawn` processes behind a shared start gate, both repeatedly calling the same authoritative `advance_od5a_durable` transaction. For all five registered arms, compare the **full** durable entity and immutable `DomainEvent` sequence against uninterrupted execution in a different SQLite file. Duplicated stage completions and unpaired leases fail.
- Multi-organization race: three independent organizational job IDs and treatment arms execute concurrently against one SQLite store, each with its own `Entity` clock and per-job physical resource definitions. Compare **every per-job** entity/event history to serial control; complete all jobs with no active physical reservation and preserve job-scoped correlations.
- Actors are separate OS processes, not separate in-memory services or threads; each opens and closes its own persistence connection. No SimPy environments or ephemeral resource objects are persisted.
- Use small hand-specified exogenous demands with microsecond-exact fractional intervals and colon-bearing IDs. No confirmatory design runs or results produced.

## Limits / ADR

SQLite **naturally serializes writes at the DB transaction boundary**; these tests demonstrate atomic multi-process job progress, not parallel commit throughput, explicit job-lease/fencing semantics, PostgreSQL concurrency or a production recurring runner. They do **not** claim the full #477 gate passed. Follow-up work must validate real publication/claim/ACK/Command/effect fencing and faults, physical instance recovery, multi-domain fanout, and a separately witnessed causal-equivalence bundle before any independent execution-freeze seal.

Historical v1 freezes, v1 scientific findings and PC6 recovery certification remain immutable.
