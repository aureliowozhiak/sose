# OD-5a v2 — Structure versus execution capacity at matched total cost

**Stage:** prospective design preregistration (not execution freeze).  
**Tracking:** #460, #461, #459, program #457.  
**Prior evidence:** Manufacturing/O2C/MRO v1 frozen results are unchanged; PR-review v1 failure is not reinterpreted.  
**Question:** In which *exogenously specified operating regimes* does reducing structural coordination/dependencies improve operational outcomes more than buying execution capacity for the same total cost?

## Falsifiable hypothesis

Let `a_cap` expand only actor execution capacity. Let `a_top` reduce a preselected dependency/handoff topology without changing actor service rates; let `a_coord` reduce preselected coordination delay without secretly changing execution capacity. Let `a_combo` combine the permitted structural transformations. Under a common fixed budget and exogenous demand/world, estimate the paired contrast of p90 item lead time and throughput for each structural arm relative to `a_cap`.

**H0:** Structural interventions do not improve p90 lead time beyond the equivalence margin while maintaining noninferior throughput, for any eligible exogenous regime.  
**H1:** An explicitly described, replicable non-null region exists. This is falsified when no region passes the registered rule. Heterogeneity and harmful regions must be reported.

No omnibus productivity index is permitted. Mechanism manipulation checks and economic constraints are independent gates; a statistically significant reduction of lead time is not enough if budget, throughput or intended mechanism checks fail.

## Arms and admissibility

1. `baseline`: original topology/capacity/cost, presented as context, **not** described as a cost-matched treatment.
2. `capacity_only`: add execution capacity while preserving queueing topology, routing, information availability, handoff graph and decision delays.
3. `topology_only`: reduce a preregistered subset of handoffs or dependency edges while preserving demand, actor capacity, service distribution and action eligibility.
4. `coordination_only`: reduce a preregistered coordination latency, preserving active service time and available actor capacity.
5. `structural_combined`: apply topology and coordination interventions together, charged for both.

Each treatment must satisfy the same lifecycle budget `B = operating_cost(H) + transition_cost + shadow_price(transition_time)` within a **1% tolerance** at design time. Otherwise declare the configuration ineligible *before observing outcomes*. Unspent budget is not silently treated as free intervention benefit. Budget-matching uses declared costs, never cost inferred from the simulated outcome.

## Exogenous regime coordinates

Freeze pre-run configured offered-load intensity `rho_nominal`, calendar availability, dependency density, routing complexity, intervention cost ratio, nominal service-time distribution and nominal coordination latency. Do **not** use realized WIP, measured queueing utilization, post-treatment waiting fraction, throughput or fraction of induced delay to assign a design regime. Those are outcomes. Configuration `model_spec_hash` and `config_epoch` must accompany all interval and intervention evidence.

Common random numbers are keyed by root seed, stream, entity identity, mechanism and logical draw index. Changing topology must not shift random draws that belong to unchanged mechanisms. If entity identity or opportunity set changes and paired CRN is not valid, register the affected streams as non-pairable and report a separate analysis.

## Outcomes and estimands

- **Primary paired estimand:** `(p90_lead_time(structural) - p90_lead_time(capacity_only)) / p90_lead_time(capacity_only)`, stratified by predeclared regime; smaller is better. If reference p90 equals zero, mark that world ineligible and report count.
- **Throughput noninferiority:** `throughput(structural) / throughput(capacity_only) >= 0.98` under the preregistered uncertainty criterion.
- **Practical improvement threshold:** at least a **5%** reduction in p90 lead time, with the associated confidence interval entirely below the -5% threshold. These thresholds are design-stage choices; changing them requires a new preregistration version.
- **Secondary descriptive outcomes:** mean/p50 lead time, WIP, throughput, tail spread, actual execution/coordination/rework actor time, elapsed waiting by declared cause, intervention operating cost, transition cost/time, and incomplete/censored items. Never infer service effort from timestamps of unrelated source events.

**Performance break-even `R*`:** within a fixed exogenous configuration stratum other than offered load, let `g_a(rho) = p90_lead_time(a, rho) / p90_lead_time(capacity_only, rho) - 1`, calculated under the fixed lifecycle cost budget. A break-even for arm `a` is an exogenously ordered `rho_nominal` where `g_a` crosses **zero** while the throughput noninferiority condition holds on both sides. This is a **performance** break-even at equal charged cost, not an unspecified currency-valued utility function. The separate practical-benefit region requires `g_a <= -0.05` and the registered confidence rule. Report every adjacent-design-point crossing bracket, whether it has uncertain status, and all regimes failing noninferiority. Do not interpolate through unobserved regimes to declare a precise root. If no bracket exists, report `nonexistent`; if multiple exist, report `nonunique` with every bracket. Do not assume monotonicity. No root search over observed outcomes is allowed to redefine configured regime coordinates.

## Analysis and design commitments

The prospective design is **32 Sobol strata over exogenous non-load coordinates × the same seven preregistered nominal-load levels** `rho_nominal ∈ {0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6}` per stratum, yielding **224 configured worlds**, with **16** CRN replications per world/arm across five arms (17,920 arm-world-replication executions). Offered load is defined against the **baseline's nominal execution capacity**, never the realized post-treatment capacity. This fully crossed structure is necessary for genuine *within-stratum* break-even brackets; a single multivariate Sobol point per load cannot identify an `R*` crossing at fixed other coordinates. A finite fixed observation horizon `H` must be selected and frozen **before** confirmatory execution. Mark the exact parameter bounds and cost schedule as **missing execution-freeze prerequisites**, not as fields that can be tuned after outcomes.

For each preregistered structural-versus-capacity contrast: compute the paired distribution, 95% confidence interval from world-grouped resampling, and Holm correction for the three structural arms. Distinguish *practical equivalence*, *statistical non-rejection*, *lack of precision*, and *falsification*; no broad efficiency claim from a null test. Publish every eligible and ineligible world, multiplicity-adjusted results, null regions, adverse regions, and sensitivity to the declared cost assumptions.

## Required manipulation checks

- Conservation of item elapsed time: item ledger intervals cover the configured observation window without gaps/overlap.
- Actor capacity conservation: `EXECUTION`, `COORDINATION`, `DEVELOPMENT`, `IDLE` and `UNAVAILABLE` cannot double-consume actor capacity.
- `cause` and `config_epoch` are durable, assigned before measurement, and do not jump or alias on restart.
- A structural intervention changes its intended topological/coordination mechanism and does not change configured service capacity, exogenous arrivals or unrelated CRN streams.
- Capacity treatment changes capacity but not the dependency graph, information timing, eligible actions or service distribution.
- All real transition costs are charged; deliberately adverse interventions must produce an auditable negative counterexample.
- Persistence recovery and uninterrupted execution produce the same canonical truth for a fixed world, with independent identities and stored evidence hashes.

## Freezes, release boundary and stop rule

This document is the **prospective design record**. It intentionally contains unfilled execution-specific choices (`H`, numeric cost schedules, design coordinate bounds, exact model/source/lock hashes). No confirmatory run is permitted while those are unfilled. The **execution freeze** must be a separate reviewed immutable, machine-readable manifest with code/source tree, `uv.lock`, `ModelSpec`, protocol hash, registered seed/design matrix, precise budget matching and result-verification contract. A design revision after outcomes cannot inherit this version's claim.

Do not alter Manufacturing/O2C/MRO v1 archives or reinterpret the PR-review v1 negative result. The scientific output is complete when the registered finite experiment publishes all arms and null/negative regions — including if H1 fails — without requiring actor exit, management replacement or A1 policy expansion. Those belong to OD-5b.
