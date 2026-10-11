# PC6 — multi-domain, multi-organization boundary OS-kill falsification

**Status:** scientific experiment for #406, independently deployable from the authoritative PostgreSQL resource-ledger work in merged #443/#446. This document freezes the expected semantics before any promotion.

## PRD — preserve typed causality under real process termination

For two independently recoverable organizations A and B, each isolated in its own operational PostgreSQL namespace, a worker may die after any durable step of a causal business workflow without losing, duplicating or inventing committed **business** evidence. Organization B must be free to finish its entire four-domain path while A's worker is dead. Once A reopens fresh database connections, its completed history must be semantically equivalent to an uninterrupted reference.

The domain graph is:

```mermaid
flowchart LR
  W["Warehouse Fulfillment: dispatch_ready"] --> L["Logistics: delivered"]
  L --> O["Order-to-Cash: invoiced"]
  O --> P["Cards Payments: settled"]
  P --> R["Record-to-Report: posted"]
```

Each organization's distinct typed `BoundaryMessage.causation_kind=boundary` links are immutable. A descendant may be published in advance but may **not** be claimed until the predecessor is ACKed, its domain Command retired and `BusinessEffectApplied` certified.

## TRD — process-death windows

One **real subprocess** is killed via `os._exit(79)` at each of the following six points for each of the four source-to-destination contracts (24 fault/contract cases). The test does not simulate death by raising an exception and closing a transaction gracefully.

| Window | Durable expectation after death | Permitted recovery |
| --- | --- | --- |
| `after_publish` | Immutable message + pending delivery | Reclaim, ACK, stage the Command, apply and certify |
| `after_claim` | Message + claimed delivery, expiring lease | Reclaim after lease timeout with a strictly greater epoch; no stale owner adoption |
| `inside_ack_before_commit` | Process killed **inside** PostgreSQL UoW after staging the Command, before commit | PostgreSQL rolls back **both** Command and ACK; lease remains claimed, no orphan receipt |
| `after_ack_command` | ACK consumption receipt and Command **both committed atomically** | Execute the original Command without another ACK or causal identity |
| `after_domain_transition` | Durable domain entity/event advanced; Command still pending | Replay same event identity idempotently, then certify once |
| `after_certificate` | Immutable certificate and Command retirement committed together | Already completed, replay strictly idempotent |

**Negative causal oracle:** after a worker dies in any window before certification, publish its typed downstream successor and attempt to claim it. The claim must return no work, not fabricate success. Meanwhile, organization B completes all four stages on its own connection. When A recovers, the already-published successor must become executable *only* after the original predecessor certificate commits.

**Semantic comparator:** reopened PostgreSQL connections read domain entity versions, full domain events, certificates, immutable messages, delivery identities/statuses, ACK consumption receipts, settlement binding, typed causal edges + semantic DAG digest, scheduled work, storage/resource records, job/sink checkpoints. Physical lease owner, number of claim attempts, lease epoch and time of retry are not confused with business causality. Final canonical digests are emitted for each death window and compared with an uninterrupted baseline.

**Required evidence artifact:** `pc6-multidomain-oskill.json` (GitHub `pc6-multidomain-boundary-oskill`). A missing or failed artifact fails PostgreSQL CI.

## ADR — real persistence, controlled reference business transitions

Use the production `BoundaryService.publish`, `claim_next`, `consume`, real PostgreSQL transactions/rollback, typed `BoundaryConsumerRegistry`, authoritative `BusinessEffectService.complete`, and the real typed causal audit. The four domain terminal outcomes in this specific protocol falsifier are **deterministic reference entity/event transitions**, with a durable explicit receivable and settlement binding. This experiment does **not** assert that real Logistics, O2C, Payments, R2R statecharts ran inside the worker subprocess. The merged real-domain proof #443/#446 separately exercises the Logistics statechart and its physical ledger, but not this four-domain frontier. The next promotion step must combine both in the same experiment.

Do not introduce a global organizational lock, do not interpret transport ACK as completion, and do not allow the original publisher to fabricate a missing certificate on behalf of a crashed consumer. Physical capacity contention has separate certified fault windows in #446; this matrix intentionally isolates causal transportation/persistence from resource scheduling.

## Promotion gates and remaining falsifiers

- PostgreSQL exact-head: all 24 actual child-process exits `79`; 24 canonical equivalences, DAG edges and domain certificates preserved, zero pending Commands, no causal overtaking.
- Python 3.12–3.14, codebase-stats and pytest coverage minimum, all chaos gates, benchmark smoke, frozen Manufacturing/O2C/MRO, and required uploaded artifact.
- **Still unproven:** simultaneous workers within *one* organizational namespace after stale fencing, real multi-domain statechart execution under all six cuts, split PostgreSQL/network failure during commit ACK uncertainty, leased job-driven autonomous cross-domain egress, physical instance allocation under concurrent legacy+authoritative pools, and non-idempotent external processors. Keep #406 OPEN.
