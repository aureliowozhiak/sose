# ADR-0007 — Versioned scientific freezes and historical replay gates

- **Status:** Accepted — via OD-0 governance acceptance (issue #458), subject to green mandatory replay/CI and merge of the reviewed acceptance PR; does not supersede v1 freezes.
- **Date:** 2026-10-09
- **Related PRD/TRD:** PRD-0001, PRD-0003; TRD-0001, TRD-0003
- **Related ADR:** ADR-0002, ADR-0005, ADR-0006
- **Trackers:** historical implementation [#397](https://github.com/brunolnetto/sose/issues/397) (closed); governance acceptance [#458](https://github.com/brunolnetto/sose/issues/458); program [#457](https://github.com/brunolnetto/sose/issues/457)

## Context

Manufacturing, O2C and MRO v1 are officially executed synthetic experiments. Their frozen provenance includes exact code/manifest identities; in particular, O2C and MRO bind the entire `src/sose` Git tree (`eeae0590f0ab84230a2cabfecd5225111d777592`) and `uv.lock` Git blob (`5902ec2400ba5998f154831d080b1e5773da7413`). Manufacturing binds its **selected file inventory and SHA-256 entries**, including `src/sose/examples/process_manifest.py`, plus its trusted preregistration manifest Git blob. Unlike O2C/MRO, Manufacturing v1 did **not** preregister a complete `src/sose` tree or `uv.lock` Git-blob identity; these cannot be invented retrospectively. Its released execution-source SHA and recorded dependency-lock digest provide additional independently auditable provenance.

A subsequent attempted Warehouse Fulfillment PC6 maturity promotion modified the current source tree, causing five frozen-v1 tests to fail. This was **correct** fail-closed behavior, but an unconditional assertion that today's `HEAD` has the old source tree prevents all future valid software evolution.

The source freeze must remain immutable, while the *location of replay verification* can be decoupled from the evolving main development tree.

## Decision

1. **Immutable protocol history.** Each official v1 manifest, released evidence archive, code-tree identity, environment lock, protocol/plan hashes and result hashes remain unchanged. Existing release tags retain their historical source commits.
2. **Development vs replay validation.** Current main CI executes current adapters and process-composition conformance. A separate **historical replay job** checks out the exact trusted frozen commit into an isolated worktree/environment, verifies the **domain-specific historical freeze** (selected file hashes and trusted preregistration anchor for Manufacturing; full source-tree and lockfile identities for O2C/MRO), executes the frozen experiment and compares canonical result hashes.
3. **Fail closed in official runners.** A v1 official runner refuses to run against any source tree or lockfile other than the frozen one. Never relax `verify_freeze` to accept a new `HEAD`.
4. **No implicit rewrite of science.** Any modification to intervention semantics, runtime, projection, eligible metric or DOE must be a new v2 preregistration/freeze, not an in-place edit to the v1 protocol or recorded outcomes.
5. **Repository test contract.** Tests of *historical frozen reproducibility* run in the frozen worktree, not the current head; current source tests ensure v1 metadata/release source references remain present and correctly documented. The separately isolated replay result becomes the authoritative anti-regression gate.
6. **Publication boundaries.** Historical release assets and SHA-256 sidecars are never overwritten. New experiments publish separate versions with their own provenance, and the comparison report states exactly which version produced each claim.

## Architecture

```mermaid
flowchart TD
  A[Current main] --> B[Current runtime and PC5/PC6 regression]
  A --> C[Historical replay coordinator]
  C --> D[Checkout trusted v1 source commit]
  D --> E[Verify manifest, full source tree, uv.lock]
  E --> F[Run frozen v1 in isolated environment]
  F --> G{Canonical result hash matches released evidence?}
  G -->|Yes| H[Historical reproducibility gate passes]
  G -->|No| I[Fail CI, preserve diagnostics]
  A --> J[Versioned v2 preregistration]
  J --> K[New independent scientific freeze]
```

## Required tests before acceptance

- CI demonstrates **current main tree differs from frozen v1** without reclassifying the historical freeze as invalid.
- Isolated replay reconstructs all documented v1 result hashes (Manufacturing, O2C, MRO).
- Tampered **preregistered** anchors fail before any official world: selected source files and trusted manifest blob for Manufacturing; full runtime tree and `uv.lock` Git identity for O2C/MRO. The isolated replay also checks each canonical output file against independently recorded digests of the corresponding published v1 bundle, not just the newly computed result hash.
- Replay fails if one canonical output differs, even when count metrics match.
- Worker interruption, dependency unavailability and incomplete replay outputs preserve staging diagnostics and do not publish success.
- New v2 source changes do not silently mutate any v1 archive or scientific claim.

## Alternatives rejected

- Replacing the frozen source identity with HEAD: destroys preregistration integrity.
- Skipping freeze checks in tests: leaves no independent scientific gate.
- Blocking all future `src/sose` changes: makes an experiment library unmaintainable.
- Treating refactoring under a new HEAD as the same v1 experiment: risks post-hoc research decisions.

## Acceptance implementation and audit evidence

The accepted policy is implemented by the separate
[`historical-organizational-v1-replay.yml`](../../../.github/workflows/historical-organizational-v1-replay.yml)
and its current-source fail-closed contract checker
[`verify_organizational_v1_replay_contract.py`](../../../scripts/verify_organizational_v1_replay_contract.py).
Acceptance is scoped to the independently verified replay mechanism; it is
**not** an acceptance of uncalibrated Organizational Dynamics causal claims.

The replay gate runs for changes to runtime sources, the dependency lock,
scientific preregistrations, replay scripts, the pinned-digest registry,
**this ADR** and its governance-regression tests. It checks out the exact
published source commit for each experiment, installs the historical
frozen environment and verifies original source identity **before** running
the official v1 experiment. The published canonical file digests are
compared to `.github/organizational-v1-published-digests.json`; the current
source cannot substitute for the pinned historical checkout.

The additional **pre-execution** governance checker validates the trusted
Git-blob SHA `410ecb050eb3943997b184e36d6f70d73d40620c` for the released
digest registry, the exact published source/result pairs, seven canonical
files per domain, and each original preregistered freeze manifest Git blob.
A simultaneous change to the workflow and its digest registry therefore
does not silently redefine the v1 science.

### Approved immutable source scopes

| Domain | Historical source | Original freeze boundary |
|---|---|---|
| Manufacturing | `125fb707e5cbed05ac19e6d43bcd0736bd4b14f6` | Selected seven-file SHA-256 inventory, trusted preregistration Git blob, published canonical result digests |
| O2C | `3c356fea6adba2d27f583d3a1469e5df1c0b651b` | Selected prerequisites **and** entire `src/sose` Git tree and `uv.lock` Git blob |
| MRO | `3c356fea6adba2d27f583d3a1469e5df1c0b651b` | Selected prerequisites **and** entire `src/sose` Git tree and `uv.lock` Git blob |

A new version of `ledger.py`, `projection.py` or `agency.py` is allowed
to evolve on current `main`, but is never a modification of v1. The
historical executable source and frozen v1 outputs remain immutable.
Intervention/protocol changes require a **new** versioned experiment freeze.

### TDD evidence and negative controls

- Tampering with any published digest, source commit, preregistered
  manifest or canonical file inventory fails before an official v1 replay.
- Substituting `main` for the pinned checkout, changing a matrix result
  hash, removing per-file SHA-256 checks, or suppressing ADR-triggered
  historical CI fails the independent current-source governance suite.
- Each historical replay reproduces the domain's registered `result_hash`
  **and every canonical evidence file SHA-256**; incomplete/staged
  evidence remains available for diagnosis and is not promoted.

**Formal acceptance gate:** this ADR reaches the default branch only through
a review-clean OD-0 pull request with passing governance-regression tests,
all three historical replay jobs, and ordinary source coverage/CI. The
earlier closed tracker #397 establishes the infrastructure but does not by
itself constitute ADR acceptance. Additional scientific results are
separately versioned and tested under OD-1 and OD-5a; this governance
decision cannot rewrite Manufacturing/O2C/MRO v1 outcomes.
