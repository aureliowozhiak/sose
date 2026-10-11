# PRD — OD-5a matched-cost structure-versus-capacity falsification (v2)

**Trackers:** #460 (design registration), #461 (future execution), #457 (OD program).  
**Release class:** preregistration of a **synthetic** experimental protocol. Not empirical validation.  
**Admission state:** DESIGN DRAFT — no confirmatory simulation authorized until the independent execution freeze.

## Problem

A simulation engine can be deterministic and restart-equivalent while still embedding unverified assumptions about organizational behavior. The OD-5a experiment must test the narrower structural hypothesis: whether altering dependencies/handoffs or reducing configured coordination latency outperforms an equivalent-cost increase in execution capacity in some **exogenously configured** demand and topology regimes.

## Research questions

1. Under equal charged lifecycle cost, what is the paired p90 lead-time difference between structure and capacity interventions?
2. Does that difference coexist with throughput noninferiority rather than simply avoiding completion of difficult work?
3. Are there clearly observed regimes of practical equivalence, reversal or harm?
4. Does a discrete, identifiable performance break-even `R*` exist across the configured nominal offered-load coordinate, or are there multiple/no crossing brackets?

## Users and non-goals

**Users:** investigators designing controlled synthetic organization experiments, reviewers verifying preregistration, and readers checking the original evidence bundles.

**Not this project:** forecasting outcomes for real organizations, fitting human work effort from GitHub timestamp gaps, exploring unregistered treatments after seeing results, proving all A1 policies or actor-management behavior, or replacing PC6/PC7/PC8 research gates.

## Decision requirements

- Fixed arm inventory: `baseline`, `capacity_only`, `topology_only`, `coordination_only`, `structural_combined`.
- Equal budget **among treated arms** to within 1% of charged lifecycle budget, not a claim that untreated baseline has the same spend.
- Exogenous configurational coordinates; post-treatment WIP/utilization/queue fractions are outcomes and **cannot** determine a regime.
- Primary estimand is paired relative p90 lead-time difference against capacity-only, plus throughput noninferiority at 0.98. Practical improvement requires at least 5% p90 improvement with the registered CI rule.
- Region-level null, harm, weak power and nonidentifiability results cannot be omitted.
- `R*` is a performance crossover bracket at equal charged cost. Do not impute a monetary utility or assume a unique monotone crossing.
- Separate reviewed **design registration** and final **execution freeze**. Missing horizon, cost schedule, bounds, root seed, source/lock/model hashes must prevent confirmatory execution.

## Acceptance

- Machine-readable and narrative design agree on arm identities, thresholds, cost accounting, statistical method and break-even semantics.
- New tests exercise positive preregistration invariants and reject circular regime coordinates and premature execution.
- Design is reviewable without inspecting any confirmatory outcomes; all earlier v1 freezes remain unchanged.
- OD-5a execution (#461) requires an independent code+data+environment freeze and scientific bundle before making any claim.

## Stop rule

Publish the complete pre-registered finite result regardless of sign, including null/adverse outcomes. No expansion of actor lifecycle or management is mandatory for OD-5a; those mechanisms belong to OD-5b.
