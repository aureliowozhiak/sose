# TRD — OD-5a deterministic structural intervention experiment v2

**Depends on:** OD-1 causal ledger contract (#459), OD-5a design registration (#460); OD-5a confirmatory execution is #461.

## 1. Reproducible world construction

Sample **64 Sobol design points**, each with **16** counter-CRN replications. Each point is fixed by *configured* offered load, calendar availability, dependency density, routing complexity, nominal service distribution and nominal coordination latency, plus declared costs. Exclude derived realized WIP, resource utilization, delay fractions and outcomes from any input regime classifier.

Each world/arm must bind `ModelSpec` identity, `config_epoch`, intervention hash, immutable root seed and CRN mechanism/entity stream identities. Counter draw indices must not depend on unrelated scheduling or execution order. If topology changes identity/opportunity sets, record that stream as nonpairable; do not claim a false paired CRN comparison.

## 2. Intervention operational contracts

| Arm | May change | Must preserve |
|---|---|---|
| Capacity | execution slots | graph, routing, coordination, nominal demand |
| Topology | preregistered handoff/dependency edges | actor execution capacity, arrival and service distributions |
| Coordination | configured handoff/decision latency | execution capacity, structure and service distributions |
| Combined | both structural changes | arrival and execution capacity |

Attach explicit cause IDs to every affected ledger item and actor allocation. Use monotonic durable `config_epoch` at each intervention effective-time boundary; conflicting overlaps are invalid. Model transition time, costs and actor `DEVELOPMENT` if charged; do not reclassify it as idle for a cheaper intervention.

## 3. Budget contract

`B(a) = operating_cost(a,H) + transition_cost(a) + shadow_price_of_transition_time(a)`. A configuration is eligible only when every *treated* arm's declared `B(a)` matches the common budget within 1%. None of these terms may depend on post-treatment performance. A transition cost of zero requires explicit justification in the execution freeze. Unspent budget, missing costs, or missing pricing invalidates matching.

## 4. Outcome and statistical contract

Paired primary response for structural arm `a`:
`g_a(rho) = p90_lead_time(a,rho)/p90_lead_time(capacity_only,rho) - 1`; reject a zero-reference denominator as reported ineligible. Require upper 95% CI below **−0.05** for practical p90 superiority and throughput ratio noninferiority **>= 0.98**. Use `Holm` multiplicity correction across exactly three structural contrasts and resample at the exogenous-world level.

Report full cohort, incomplete/censored items, uncertainty, adverse/null/unidentifiable regions, cost accounting and sensitivity. Comparisons may not be retuned after any confirmatory result inspection. Negative controls include an intentionally harmful structural change and a capacity-only change forbidden from changing routing.

## 5. Break-even R*

For each arm and fixed stratum of the other exogenous coordinates, sort **registered design points by `rho_nominal`**. Report every adjacent pair bracketing a zero sign crossing of `g_a`, conditional on throughput noninferiority on both sides. Do not assume continuity or monotonicity and do not interpolate through unsampled regimes to advertise an exact `R*`. Report `nonexistent`, `nonunique` or `insufficient precision` as appropriate.

Performance break-even is **not** a monetary net-present-value crossing; costs have already been matched. The practical 5% superiority region is a distinct assertion.

## 6. Runtime/restart oracle

Each mechanism change must create causal, independently verifiable evidence: before/after topology, intervention hash, actor capacities, item/actor ledgers, persisted clock and job state, and cost entries. Interrupted and continuous fixed-world runs must have identical immutable business state, ledger partitions, causation, scheduled triggers and charge totals. Uncertainty about any committed event is resolved from durable truth, not client success signals.

## 7. Mandatory execution-freeze gate

**Not satisfied by this TRD.** The later reviewed `#461` freeze must supply numeric coordinate bounds, horizon H, cost and transition-time shadow prices, all arm source implementations, exact source+uv.lock blob IDs, models, root seed, sample/replication matrix, expected shape of scientific bundle, independent SHA-256 verifier, and signed-off accept/reject evidence. Old v1 manifests/results are never rewritten.

This TRD describes what to build and falsify; it is not a claim that any specified intervention already exists or has passed validation.
