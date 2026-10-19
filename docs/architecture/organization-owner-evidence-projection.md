# #496 W3a — owner-qualified read-side organization event projection

This is a **bounded, read-only observation** of selected StateChart event
evidence, not a runnable multi-domain organization. An
`OrganizationDefinition` must pass the real catalog/process-manifest/consumer
registry admission rules (ADR-0008). Only the declared exact StateChart
entity type(s) of each component and its durable owner are eligible for selection.
A selected event must additionally be a correctly shaped `entity.state_transition`
with explicit string trigger/source/target fields. Other events of the same
entity type are not silently promoted to StateChart evidence. This structural
check is not a full Command/causation attestation or authorization.

One `Persistence.events()` call supplies the observed event window; events
are grouped into each named component in **owner-local append order**.
`component_id`, `owner_id`, definition fingerprint, version/config epoch,
registered entity types and *declared* job IDs remain distinguishable. Foreign
organization events and unregistered event families are not promoted into
component truth. An event having the entity type of another admitted component
but arriving under the wrong admitted owner fails closed. Duplicate observed
event identity and ambiguous reused owner IDs across domains are rejected.

The API is observational only:

- **Not complete**: It does not yet join source entities, Commands, queue
  messages/claims, scheduled work, resource demands/occupancy, boundary ACKs,
  simulation positions, config migration or real job progress. A declared job
  ID is **not** evidence that a job has run.
- **Not globally atomic**: One event-tuple read is not a coordinated global
  snapshot of independent owners. No global owner/clock/lock/transaction is
  introduced. The event order must never be interpreted as a cross-org causal
  relation; typed source/receipt edges are the only eligible causal evidence.
- **Not authorization**: No new installed policy/calendar/cost model; no
  physical-pool grant, preemption or release. All such admission continues
  to fail closed pending #496/#477 independent certification.
- **Not domain-conformance proof**: These tests use genuine registration
  metadata and persistence adapters to attest ownership and restart stability,
  not to claim every domain has a certified composed effect.

This slice is a starting falsifier for the #496 read-model boundary.
It **does not close** #496 or release heterogeneous #497, physical #477
or prospective OD-5a #461.
