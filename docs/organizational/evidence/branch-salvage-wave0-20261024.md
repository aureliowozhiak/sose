# Wave 0 salvage: source and closure certificate (2026-10-24)

This file is a **development and archival inventory**, NOT a scientific protocol,
new preregistration, experiment result, or permission to validate Stage-2.

## Vocabulary: three independent tracks

- **Wave 0 / #560**: find unique unmerged branch changes, recover legitimate
  source/test/evidence, and only then retire SHA-pinned historical refs.
- **OD-0 / #458**: governance of immutable historical v1 scientific freezes,
  **closed** with ADR-0007 Accepted. It is NOT this branch-salvage wave.
- **Composition roadmap W1-W5 / #494**: a separate technical/scientific DAG.
  Physical owner authority #545 blocks W2 in salvage #563; it must not
  retroactively block accepted OD-0/v1 freezes.

## Audited Wave 0 state at main fcca6fd6 (snapshot, not a live dashboard)

| Issue | State at snapshot | Source-bound result | Outstanding gate |
| --- | --- | --- | --- |
| #561 | CLOSED | #570, #571 and #567 merged; 15 original detached Stage-2 blobs archived byte-identically | Retire detached ref only after exact-SHA guard and parent receipt |
| #562 | CLOSED | #569 and #572 merged; typed reference and A0/A1 BATCHING-only implementation | No extension to unimplemented A1 policies |
| #563 | OPEN | Four modern service-capacity and seven restart-equivalence tests supersede the four legacy W1 scenarios | W2 independent PostgreSQL owner/fence/ACK recovery after #545 |
| #564 | OPEN | O1 source-identity adversarial tests #574 merged | O2 source-paired review observability; separately checked from CI-job coverage |
| #565 | OPEN | S1 original synthetic draft versus published canonical verified as *different experiments* | S1 source-bound regression and explicit NO-GO on retrospective S2 thresholds |
| #566 | CLOSED | J1 source-pinned no-J2 disposition recorded for five orphans | Parent must still certify eligible SHA-fenced retirement |

The 46 branches reported by GitHub at this snapshot include main and detached
scientific and nonmerged historical refs. **No new ref deletion is claimed.**

## S1 synthetic source forensic verdict (#565)

The orphan source branch
\`automation/synthetic-organizational-canonical-v1-draft\` points to
\`17bbdbddb7dba65cbca7728a6ce65118fe578c9d\`. Its
\`SyntheticVerificationCriteria\` proposed a maximum relative stable-world
error of 0.25 and minimum direction-recovery rate of 0.85, but there is **no
demonstrated independent, pre-outcome preregistration** authorizing those
thresholds as acceptance criteria for the published current reference-v1.

The accepted, already-published reference is a *different* experiment:

| Property | Historical orphan | Published reference v1 |
| --- | --- | --- |
| Root seed | 20261008 | 20261007 |
| Design seed | 20261007 | 20261007 |
| Sample size | 24 | 12 |
| Replications | 4 | 16 |
| Regimes/arms | Capacity/policy/automation/structural | Baseline/capacity-up/automation-rework |
| Published report | NOT the frozen reference-v1 | versioned reference-v1 evidence with manifest |

Reference-v1 protocol blob SHA-1:
\`f1a865a146fa4a3d457c65670d3c69fa0d91dd05\`.
Reference-v1 manifest blob SHA-1:
\`ec6e97f60dadb692a3ff18745aca3249079959b3\`.
Published result interpretation remains *synthetic mechanistic verification*,
not empirical validation of organizations or reviewer service effort.
The existing v1 protocol does not contain the orphan's two criteria thresholds.

### Decision — S1 is source-audited; S2 is scientifically NO-GO for v1

Never introduce retrospective 0.25/0.85 pass/fail labels or an inferred
\`criteria_digest\` into frozen v1, even when its observed outcome would pass.
Do not cherry-pick orphan seed, generator or policy arms. A future **newly
versioned, prospective** verifier could be implemented only after an
independently persisted/timestamped threshold and source-registration
commitment **before** new outcomes are exposed. The existing published v1
cannot satisfy that temporal preregistration after the fact. The absence of
an S2 PR is an intentional bounded stop, not a missing implementation.
Tests beside this note guard the source and protocol boundary.

## Branch retirement certificate format (per ref)

Before physical deletion, record: remote full ref, current Git HEAD SHA,
original source SHA, original file/blob inventory, accepted replacement
commit or evidence-class no-PR disposition, scientific retention decision,
independent reviewer, and successful *exact-SHA* match immediately before
deletion. A branch with unsupported assertions or exclusive scientific
history is **retained**, even if its earlier PR was closed/merged.
GitHub merge/squash does not imply byte or predicate equivalence.

Issue #560 is the live authoritative tracker and remains OPEN until its
child gates and actual retirement/retention receipts are complete.
