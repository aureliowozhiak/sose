# OD-1 — Causal accounting and time-versioned configuration

**Trackers:** [#459](https://github.com/brunolnetto/sose/issues/459), [OD program #457](https://github.com/brunolnetto/sose/issues/457), [OD-5a v2 preregistration #460](https://github.com/brunolnetto/sose/issues/460).

## Measurement contract

This is the current-source **instrumentation** release, not a new official experiment or empirical causal validation.

- `AccountingEvent.cause` records an explicit immutable provenance identity. Projected item intervals retain the cause of their **winning category under preregistered precedence**, never an arbitrary active event or first arrival.
- When two overlapping events of the same winning category claim conflicting causes, projection **fails closed**. When different item categories overlap, the prevailing category supplies the primary cause while labels still include all observational context.
- `config_epoch` is a nonnegative integer for a committed configuration revision. Every versioned record must also carry its `model_spec_hash`; an epoch may not be silently rebound to a different configuration identity. Cross-epoch overlaps fail closed; contiguous epochs cannot decrease.
- `ActorCategory.DEVELOPMENT` is **paid, allocated actor-time**, not `IDLE` or `UNAVAILABLE`. It consumes finite capacity and cannot overlap an executing actor in serial mode. Fractional multitasking may overlap within the **same** configuration epoch, respecting total capacity ≤1.
- ModelSpec hash and epoch are distinct coordinates: the hash denotes semantic configuration; the epoch denotes **when it became effective** for a particular timeline. An explicit interval split with `next_config_epoch` records a transition rather than silently reusing the earlier epoch.
- Optional new event fields permit loading legacy persisted observations without inventing historical causes or epochs; original frozen Manufacturing/O2C/MRO v1 sources and outputs remain untouched.

## TDD falsification

Required tests verify idempotent `dump_state` → `from_state`, time and actor-capacity conservation, winning-class provenance, conflicting source rejection, epoch collision/regression rejection, distinct source hashes and a valid model revision boundary.

## Limits and downstream dependencies

These are *instrument definitions*, not evidence that managerial behavior exists in the simulated world. OD-5a will preregister its event causes, structural arms, costs, horizon, matched CRN and break-even estimand **before confirmatory execution**. Actor exit, reassignments, managerial sham interventions and policy-specific behavioral dynamics remain OD-2/3/4.

Migration support is additive and in-place only for **current** data formats. No scientific v1 manifest, preregistration hash or original evidence bundle may be regenerated or rewritten.
