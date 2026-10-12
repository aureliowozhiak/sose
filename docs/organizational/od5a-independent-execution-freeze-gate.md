# OD-5a v2 — Independent execution-freeze admission (PRD / TRD / ADR)

**Tracker:** #461 / #457. **Scientific status:** INDEPENDENT GATE IMPLEMENTATION, **NOT SEALED**. Neither accepted preregistration #470 nor operational prototype #473 nor pending recovery oracle #474 authorizes confirmatory runs.

## PRD — why a separate freeze is required

OD-5a design registration determines estimands, treatment comparisons, 32 non-load Sobol strata × seven offered-load values × 16 replications × five arms, Holm 21-comparison family, and publication of null/adverse/nonidentifiable regimes. An **independent** execution freeze binds final runnable code and environment to concrete and mechanistically meaningful configurations *before* any confirmatory outcomes.

The committed `od5a-execution-freeze-v2-draft.json` intentionally contains `UNSET` placeholders and `stage=NOT_ADMITTED`; it MUST be rejected. Changing `stage` alone is insufficient and forbidden as a way to bypass admission.

## TRD — finite seal procedure

1. Merge and reproduce #474, plus cross-adapter execution/causal conformance and the persistent worker-claim/fencing tests; no new organizational mechanism is allowed unless required to meet a preregistered manipulation.
2. Register the six **exogenous** Sobol bounds and transformations to physical parameters: calendar availability, dependency density, routing complexity, nominal service distribution, nominal coordination latency and declared intervention cost ratio. Avoid WIP/utilization/queue-derived coordinates.
3. Fix total horizon H/warmup, baseline-capacity offered-load denominator, complete lifecycle operating/transition/transition-time shadow-cost rates and the actual integer slot identities; reject unmatched treatment costs above 1%.
4. Fix service family, deterministic dependency-DAG constructor, calendar/physical resource policy, immutable seed, mechanism/entity/draw-index counter-CRN rule, and independently review pairability and censoring eligibility.
5. After final implementation merge, record checked-out **Git OID for `src/sose`**, SHA-256 of `uv.lock`, SHA-256 of design registration, all five model/admission hashes, audit-verifier/output-schema hashes and the signed recovered-worker evidence digest.
6. Replace draft with a new versioned execution manifest **in a separate review PR**. The validation gate must reject any remaining placeholder, missing hash, duplicate JSON key, nonfinite bounds, changed arm, changed geometry, stale checked-out code/lock or altered scientific observation rule. Only a reviewed, entirely admitted immutable manifest permits the 17,920-run invocation.
7. Seal manifest digest and timestamp **before** generating any confirmatory outcomes. Run the registered design without retrospective changes, publish all results including failures, censoring and unidentifiable R*.

## ADR — why not embed hashes directly into engine source

The source-tree Git OID and the `uv.lock` digest belong to independent scientific provenance. They are not implicit versions inferred from a changing `main`. A checked-out source/lock mismatch must fail closed.

This gate validates syntax, finite economic admission and local source/lock bytes; it does **not** independently establish empirical validity, causal mechanism fidelity or cryptographically signed review approval. Those are separate evidence artifacts and a human review decision, not flags to autogenerate.

The legacy v1 Manufacturing/O2C/MRO freezes, PR-review negative result and PC6 certification scope are immutable and untouched.


The pre-execution identity verifier requires a **pristine source checkout**: tracked, staged, untracked **and Git-ignored** files under `src/sose` all invalidate the seal. In particular, ignored native extension modules (`*.so`/`*.pyd`) may alter Python imports while leaving `HEAD:src/sose` unchanged. Validate in a fresh checkout without generated source-tree artifacts; never bypass this check by relying solely on the committed Git tree OID.


## Fresh-checkout verifier protocol (P1 remediation)

Run the fail-closed check from an **unmodified, artifact-free checkout** using `python -I -B scripts/od5a_verify_execution_freeze.py --root . --manifest path/to/approved.json`. The CLI switches on `sys.dont_write_bytecode` **before importing any SOSE module**, so an editable Python installation will not create ignored `src/sose/**/__pycache__` directories and invalidate its own checkout. Existing caches, other ignored files, generated native extensions and any untracked executable source still cause rejection; remove them by creating a **fresh checkout**, not by weakening admission.

Verification does not trust `git status` alone: every tracked regular source file is independently checked against its frozen `HEAD` Git blob bytes and mode, while all source symlinks are rejected, detecting `assume-unchanged` or `skip-worktree` index flags. The source Git tree OID, actual `uv.lock` bytes and preregistration payload SHA-256 must all agree with the prospective manifest. Even successful admission **does not** constitute scientific approval or authorize confirmatory runs; the committed example remains `NOT_ADMITTED`.


## P1 scientific admission hardening

- **Source symlinks are forbidden in the frozen `src/sose` tree.** Hashing a symlink's own Git blob does not bind bytes of an external target; a target outside the source tree may change silently. This gate therefore rejects both tracked symlinks and a tracked file replaced by a worktree symlink, even when the frozen tree OID would otherwise match.
- **Zero transition costs require a prospective, substantive explanation.** Every treated-arm cost tuple still fixes operating expense, transition expense, transition downtime and shadow price. When `transition_cost == 0`, the same arm must include `zero_transition_cost_justification` (nonempty, at least 20 characters, and no UNSET/TBD). The explanation is part of the sealed digest and requires independent substantive review; it is not an automatic assertion that a treatment is economically free. A positive transition cost must not carry that optional field.


## Checkout-bound verifier import

The cold-start CLI parses `--root` **before** any SOSE import, sets `sys.dont_write_bytecode`, rejects source-directory/module symlinks, directly executes only the validated `od5a_execution_freeze.py` byte snapshot in its own isolated module namespace **without** adding `<root>/src` to `sys.path` or importing the organizational package initializer. It fails closed if a SOSE module was already imported from another environment. A regression runs with a deliberately broken foreign SOSE distribution *earlier* in `PYTHONPATH`; only the requested checkout's verifier is allowed to run. This does not replace verification of all tracked source bytes and ignored artifacts.


## Trusted pre-import bootstrap (P1 remediation)

The executable `scripts/od5a_verify_execution_freeze.py` is the independent trust boundary for a prospective freeze. Before importing **any** `sose` module, it reads the manifest with duplicate-key rejection and uses only the Python standard library plus Git to verify: the exact Git root; SHA-256 of the invoked bootstrap against `verifier_sha256`; byte hashes of `uv.lock` and the preregistration; exact `HEAD:src/sose` tree OID; status including ignored/untracked files; and the content/mode of **every** tracked source Git blob without trusting index `assume-unchanged` or `skip-worktree`. Source symlinks fail closed. After that preflight it retains the exact bytes inspected for the verifier module and executes them via `compile` in an isolated module namespace, without making unchecked `src/` sibling modules importable. The executed verifier redundantly checks provenance before emitting the approved digest.

The manifest digest must be independently approved and sealed; this self-check is an integrity constraint, not a trusted signature. The `verifier_sha256` field denotes the bootstrap script's actual content bytes, not an arbitrary shape-valid placeholder. The checked-in `NOT_ADMITTED` draft remains unusable for confirmatory execution.


## Required isolated interpreter

Always launch with **`python -I -B`**. The trusted bootstrap aborts before any file-backed standard-library import unless both `sys.flags.isolated` and the **interpreter-start** `sys.flags.dont_write_bytecode` are set. Python `-I` removes untrusted `PYTHONPATH`, user-site imports and script-directory shadowing (for example, an attacker-controlled `argparse.py`); `-B` additionally suppresses all bytecode writes. A nonisolated Python process can execute a foreign `sitecustomize` before script startup, which an in-script check cannot retroactively prevent. Running the script without either `-I` or `-B` is **not** an admitted verification mode and must return a failure, not a scientific success.


## Preflight byte snapshot, not package import

The verifier module is executed from the **identical immutable byte string** read during the Git blob scan. It is not re-read later from a potentially changed pathname; it does not execute `sose/organizational/__init__.py` or import from a generic, unchecked `src/` path. A regression places a deliberately malicious `src/pydantic.py` sibling outside the frozen `src/sose` tree and proves that neither the package initializer nor the sibling executes. This reduces the trusted executable surface of the freeze itself.
