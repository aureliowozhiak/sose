"""OD-5a independent execution-freeze admission: contracts before outcomes."""
from __future__ import annotations

from copy import deepcopy

import pytest

from sose.organizational.od5a_execution_freeze import (
    validate_od5a_execution_freeze,
)


def _manifest():
    arms = (
        "baseline", "capacity_only", "topology_only", "coordination_only",
        "structural_combined",
    )
    coordinates = (
        "calendar_availability", "dependency_density", "routing_complexity",
        "nominal_service_distribution", "nominal_coordination_latency",
        "declared_intervention_cost_ratio",
    )
    return {
        "protocol_id": "od5a-structure-capacity-v2",
        "stage": "execution_freeze",
        "source_tree_oid": "a" * 40,
        "uv_lock_sha256": "b" * 64,
        "preregistration_sha256": "c" * 64,
        "model_spec_hashes": {a: "d" * 64 for a in arms},
        "admission_hashes": {a: "e" * 64 for a in arms},
        "nonload_bounds": {name: {"low": 0.2, "high": 0.8} for name in coordinates},
        "coordinate_mapping": {
            name: {"mapping_id": f"physical:{name}:v1", "units": "dimensionless"}
            for name in coordinates
        },
        "design_seed": 17,
        "root_seed": 123,
        "n_strata": 32,
        "load_grid": [0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6],
        "replications": 16,
        "arms": list(arms),
        "run_count": 17920,
        "horizon": 100.0,
        "warmup": 10.0,
        "baseline_nominal_capacity": 1.0,
        "service_distribution_family": "registered_lognormal_v1",
        "dependency_graph_constructor": "registered_dag_v1",
        "calendar_rule": "registered_calendar_v1",
        "physical_resource_policy": "registered_finite_slots_v1",
        "cost_schedule": {
            a: {
                "operating_cost_at_horizon": 8.0, "transition_cost": 1.0,
                "transition_time": 1.0, "shadow_price_per_transition_time": 1.0,
            } for a in arms[1:]
        },
        "crn_streams": {
            "arrival": "arrivals:v1", "service": "service:v1",
            "coordination": "coordination:v1",
            "entity_identity": "stable_item_id",
            "draw_index": "fixed_mechanism_opportunity_index",
        },
        "pairability_evidence_sha256": "f" * 64,
        "recovery_evidence_sha256": "0" * 64,
        "verifier_sha256": "1" * 64,
        "output_schema_sha256": "2" * 64,
        "censoring_rule": "registered_arrival_cohort_v1",
    }


def test_complete_prospective_freeze_has_deterministic_hash():
    manifest = _manifest()
    first = validate_od5a_execution_freeze(manifest)
    assert len(first) == 64
    assert first == validate_od5a_execution_freeze(dict(reversed(list(manifest.items()))))
    altered = deepcopy(manifest)
    altered["horizon"] = 200.0
    assert validate_od5a_execution_freeze(altered) != first


@pytest.mark.parametrize("change,pattern", [
    (lambda m: m.update({"horizon": "UNSET_AT_EXECUTION_FREEZE"}), "UNSET"),
    (lambda m: m.update({"outcomes": {"p90": 5}}), "unexpected"),
    (lambda m: m["nonload_bounds"].update({"realized_WIP": {"low": 0, "high": 1}}), "coordinates"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"operating_cost_at_horizon": 3}), "budget"),
    (lambda m: m.update({"run_count": 64}), "17,920"),
    (lambda m: m.update({"uv_lock_sha256": "not-a-digest"}), "hash"),
    (lambda m: m.update({"horizon": float("nan")}), "finite"),
    (lambda m: m.update({"design_seed": True}), "seed"),
    (lambda m: m["coordinate_mapping"].pop("routing_complexity"), "coordinate mapping"),
    (lambda m: m["crn_streams"].update({"service": "arrivals:v1"}), "unique"),
    (lambda m: m.update({"stage": "design_preregistration"}), "execution_freeze"),
])
def test_freeze_rejects_underspecified_or_post_hoc_contracts(change, pattern):
    manifest = _manifest()
    change(manifest)
    with pytest.raises(ValueError, match=pattern):
        validate_od5a_execution_freeze(manifest)


def test_draft_cannot_be_misrepresented_as_approved_execution_freeze():
    draft = _manifest()
    draft["recovery_evidence_sha256"] = "UNSET"
    with pytest.raises(ValueError, match="UNSET"):
        validate_od5a_execution_freeze(draft)


@pytest.mark.parametrize("mutation", ["tracked", "staged", "untracked", "ignored", "assume_unchanged"])
def test_freeze_refuses_dirty_source_even_if_git_head_tree_matches(tmp_path, mutation):
    """git rev-parse HEAD:src/sose alone ignores the code actually executed."""
    from hashlib import sha256
    import subprocess

    root = tmp_path
    (root / "src/sose").mkdir(parents=True)
    prereg = root / "docs/organizational/preregistration/od5a-structure-capacity-v2-design.json"
    prereg.parent.mkdir(parents=True)
    prereg.write_text('{"protocol_id":"od5a-structure-capacity-v2"}')
    (root / "src/sose/reference.py").write_text("VALUE = 1\n")
    (root / "uv.lock").write_text("locked-dependencies")
    (root / ".gitignore").write_text("*.so\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-qm", "fixture"], cwd=root, check=True)
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD:src/sose"], cwd=root, text=True,
    ).strip()
    manifest = _manifest()
    manifest["source_tree_oid"] = tree
    manifest["uv_lock_sha256"] = sha256((root / "uv.lock").read_bytes()).hexdigest()
    manifest["preregistration_sha256"] = sha256(prereg.read_bytes()).hexdigest()
    from sose.organizational.od5a_execution_freeze import verify_od5a_checkout_identity
    verify_od5a_checkout_identity(manifest, root)

    if mutation in {"untracked", "ignored"}:
        filename = "injected.so" if mutation == "ignored" else "injected.py"
        (root / "src/sose" / filename).write_bytes(b"untrusted-runtime-payload")
    else:
        (root / "src/sose/reference.py").write_text("VALUE = 2\n")
        if mutation == "staged":
            subprocess.run(["git", "add", "src/sose/reference.py"], cwd=root, check=True)
        if mutation == "assume_unchanged":
            subprocess.run(
                ["git", "update-index", "--assume-unchanged", "src/sose/reference.py"],
                cwd=root, check=True,
            )
    with pytest.raises(ValueError, match="dirty|mismatch"):
        verify_od5a_checkout_identity(manifest, root)


@pytest.mark.parametrize("foreign_first", [False, True])
@pytest.mark.parametrize("unfrozen_src_sibling", [False, True])
def test_fresh_checkout_cli_does_not_dirty_itself_with_python_bytecode(
    tmp_path, foreign_first, unfrozen_src_sibling,
):
    """Cold-start verifier uses isolated interpreter from a fresh checkout."""
    from hashlib import sha256
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    checkout = Path(tmp_path)
    repository = Path(__file__).resolve().parents[4]
    package = checkout / "src/sose"
    (package / "organizational").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "organizational/__init__.py").write_text("")
    (package / "organizational/od5a_execution_freeze.py").write_bytes(
        (repository / "src/sose/organizational/od5a_execution_freeze.py").read_bytes()
    )
    (checkout / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    if unfrozen_src_sibling:
        (checkout / "src/pydantic.py").write_text(
            "raise RuntimeError('UNFROZEN_SIBLING_EXECUTED')\n"
        )
    (checkout / "uv.lock").write_text("locked")
    prereg = checkout / "docs/organizational/preregistration/od5a-structure-capacity-v2-design.json"
    prereg.parent.mkdir(parents=True)
    prereg.write_text('{"protocol_id":"od5a-structure-capacity-v2"}')
    subprocess.run(["git", "init", "-q"], cwd=checkout, check=True)
    subprocess.run(["git", "add", "."], cwd=checkout, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "-qm", "pristine-fixture"],
        cwd=checkout, check=True,
    )
    manifest = _manifest()
    manifest["source_tree_oid"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD:src/sose"], cwd=checkout, text=True,
    ).strip()
    manifest["uv_lock_sha256"] = sha256((checkout / "uv.lock").read_bytes()).hexdigest()
    manifest["preregistration_sha256"] = sha256(prereg.read_bytes()).hexdigest()
    manifest["verifier_sha256"] = sha256(
        (repository / "scripts/od5a_verify_execution_freeze.py").read_bytes()
    ).hexdigest()
    manifest_path = checkout / "execution-freeze.json"
    manifest_path.write_text(json.dumps(manifest))
    env = {**os.environ, "PYTHONPATH": str(checkout / "src")}
    if foreign_first:
        foreign = checkout / "foreign_src/sose/organizational"
        foreign.mkdir(parents=True)
        (foreign.parent / "__init__.py").write_text("")
        (foreign / "__init__.py").write_text("")
        (foreign / "od5a_execution_freeze.py").write_text(
            "raise RuntimeError('FOREIGN_VERIFIER_EXECUTED')\n"
        )
        (foreign.parent.parent / "argparse.py").write_text(
            "raise RuntimeError('SHADOW_ARGPARSE_EXECUTED')\n"
        )
        env["PYTHONPATH"] = str(checkout / "foreign_src") + os.pathsep + env["PYTHONPATH"]
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    # A temporary, foreign test-checkout is *not* production SOSE source.
    # Do not let coverage's subprocess hook register cloned source files as
    # extra modules, artificially depressing the global coverage gate.
    for key in tuple(env):
        if key.startswith("COV_CORE_") or key == "COVERAGE_PROCESS_START":
            env.pop(key)
    subprocess.run(
        [sys.executable, "-I", "-B", "-S",
         str(repository / "scripts/od5a_verify_execution_freeze.py"),
         "--root", str(checkout), "--manifest", str(manifest_path)],
        cwd=checkout, env=env, check=True, capture_output=True, text=True,
    )
    assert not list(package.rglob("__pycache__"))
    assert not list(package.rglob("*.pyc"))


def test_execution_freeze_rejects_any_tracked_source_symlink(tmp_path):
    """A symlink target outside frozen src can change while Git-tree OID stays fixed."""
    from hashlib import sha256
    import subprocess

    root = tmp_path
    (root / "src/sose").mkdir(parents=True)
    (root / "external.py").write_text("VALUE = 1\n")
    (root / "src/sose/plugin.py").symlink_to("../../external.py")
    (root / "uv.lock").write_text("locked")
    prereg = root / "docs/organizational/preregistration/od5a-structure-capacity-v2-design.json"
    prereg.parent.mkdir(parents=True)
    prereg.write_text("{}")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "-qm", "tracked external symlink"], cwd=root, check=True,
    )
    manifest = _manifest()
    manifest["source_tree_oid"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD:src/sose"], cwd=root, text=True,
    ).strip()
    manifest["uv_lock_sha256"] = sha256((root / "uv.lock").read_bytes()).hexdigest()
    manifest["preregistration_sha256"] = sha256(prereg.read_bytes()).hexdigest()
    from sose.organizational.od5a_execution_freeze import verify_od5a_checkout_identity
    with pytest.raises(ValueError, match="symlink"):
        verify_od5a_checkout_identity(manifest, root)


def test_zero_transition_cost_requires_prospectively_registered_justification():
    manifest = _manifest()
    for cost in manifest["cost_schedule"].values():
        cost["transition_cost"] = 0.0
    with pytest.raises(ValueError, match="zero transition cost"):
        validate_od5a_execution_freeze(manifest)

    for cost in manifest["cost_schedule"].values():
        cost["zero_transition_cost_justification"] = (
            "The treatment has no setup cost under this preregistered "
            "accounting boundary; all ongoing and time-shadow costs remain charged."
        )
    digest = validate_od5a_execution_freeze(manifest)
    assert len(digest) == 64
    manifest["cost_schedule"]["topology_only"]["zero_transition_cost_justification"] = "UNSET"
    with pytest.raises(ValueError, match="UNSET"):
        validate_od5a_execution_freeze(manifest)


@pytest.mark.parametrize("mutate, error", [
    (lambda m: m.update({"protocol_id": "not-od5a"}), "protocol"),
    (lambda m: m.update({"source_tree_oid": "wrong"}), "hash"),
    (lambda m: m["model_spec_hashes"].pop("baseline"), "five registered arms"),
    (lambda m: m["admission_hashes"].update({"capacity_only": "unknown"}), "hash"),
    (lambda m: m["nonload_bounds"].pop("calendar_availability"), "coordinates"),
    (lambda m: m["nonload_bounds"]["calendar_availability"].update({"other": 4}), "bound"),
    (lambda m: m["nonload_bounds"]["calendar_availability"].update({"low": 1.0}), "increasing"),
    (lambda m: m["nonload_bounds"]["calendar_availability"].update({"high": float("inf")}), "finite"),
    (lambda m: m["coordinate_mapping"]["calendar_availability"].pop("units"), "mapping"),
    (lambda m: m["coordinate_mapping"]["calendar_availability"].update({"units": ""}), "nonempty"),
    (lambda m: m.update({"root_seed": -1}), "seed"),
    (lambda m: m.update({"n_strata": 31}), "32"),
    (lambda m: m.update({"load_grid": [0.4, 0.6]}), "load grid"),
    (lambda m: m.update({"replications": 15}), "16"),
    (lambda m: m.update({"arms": list(reversed(m["arms"]))}), "five fixed arms"),
    (lambda m: m.update({"warmup": 100.0}), "warmup"),
    (lambda m: m.update({"baseline_nominal_capacity": 0}), "positive"),
    (lambda m: m.update({"service_distribution_family": ""}), "nonempty"),
    (lambda m: m["cost_schedule"].pop("topology_only"), "four treatment"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"unknown": 8.0}), "lifecycle"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"transition_cost": -1.0}), "negative"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"operating_cost_at_horizon": float("nan")}), "finite"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"transition_cost": 0.0}), "zero transition cost"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"zero_transition_cost_justification": "unnecessary"}), "invalid"),
    (lambda m: m["cost_schedule"]["topology_only"].update({"shadow_price_per_transition_time": 0}), "priced"),
    (lambda m: m["crn_streams"].pop("draw_index"), "stream identities"),
    (lambda m: m["crn_streams"].update({"entity_identity": ""}), "nonempty"),
    (lambda m: m["crn_streams"].update({"entity_identity": "UNSET"}), "UNSET"),
])
def test_prospective_freeze_rejects_every_unbound_configuration_axis(mutate, error):
    manifest = _manifest()
    mutate(manifest)
    with pytest.raises(ValueError, match=error):
        validate_od5a_execution_freeze(manifest)


def test_execution_freeze_json_rejects_duplicate_keys_or_non_object(tmp_path):
    from sose.organizational.od5a_execution_freeze import load_od5a_execution_freeze

    source = tmp_path / "manifest.json"
    source.write_text('{"protocol_id":"x","protocol_id":"y"}')
    with pytest.raises(ValueError, match="duplicate execution-freeze key"):
        load_od5a_execution_freeze(source)
    source.write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        load_od5a_execution_freeze(source)


@pytest.mark.parametrize("field", ["uv.lock", "preregistration"])
def test_checkout_refuses_lockfile_or_registered_protocol_byte_drift(tmp_path, field):
    from hashlib import sha256
    import subprocess
    from sose.organizational.od5a_execution_freeze import verify_od5a_checkout_identity

    root = tmp_path
    (root / "src/sose").mkdir(parents=True)
    (root / "src/sose/core.py").write_text("x = 1\n")
    prereg = root / "docs/organizational/preregistration/od5a-structure-capacity-v2-design.json"
    prereg.parent.mkdir(parents=True)
    prereg.write_text("{}")
    (root / "uv.lock").write_text("uv-v1")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=t@example.com",
                    "commit", "-qm", "fixture"], cwd=root, check=True)
    manifest = _manifest()
    manifest["source_tree_oid"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD:src/sose"], cwd=root, text=True,
    ).strip()
    manifest["uv_lock_sha256"] = sha256((root / "uv.lock").read_bytes()).hexdigest()
    manifest["preregistration_sha256"] = sha256(prereg.read_bytes()).hexdigest()
    verify_od5a_checkout_identity(manifest, root)
    if field == "uv.lock":
        (root / "uv.lock").write_text("uv-v2")
    else:
        prereg.write_text('{"altered":"after-freeze"}')
    with pytest.raises(ValueError, match="independent frozen file hash"):
        verify_od5a_checkout_identity(manifest, root)


def test_cold_start_rejects_assume_unchanged_code_before_import(tmp_path):
    """No untrusted SOSE byte executes until a stdlib bootstrap proves HEAD bytes."""
    from hashlib import sha256
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(tmp_path)
    repo = Path(__file__).resolve().parents[4]
    src = root / "src/sose/organizational"
    src.mkdir(parents=True)
    (src.parent / "__init__.py").write_text("")
    (src / "__init__.py").write_text("")
    target = src / "od5a_execution_freeze.py"
    target.write_bytes(
        (repo / "src/sose/organizational/od5a_execution_freeze.py").read_bytes()
    )
    (root / "uv.lock").write_text("locked")
    prereg = root / "docs/organizational/preregistration/od5a-structure-capacity-v2-design.json"
    prereg.parent.mkdir(parents=True)
    prereg.write_text("{}")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com",
         "commit", "-qm", "pristine"],
        cwd=root, check=True,
    )
    m = _manifest()
    m["source_tree_oid"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD:src/sose"], cwd=root, text=True,
    ).strip()
    m["uv_lock_sha256"] = sha256((root / "uv.lock").read_bytes()).hexdigest()
    m["preregistration_sha256"] = sha256(prereg.read_bytes()).hexdigest()
    m["verifier_sha256"] = sha256(
        (repo / "scripts/od5a_verify_execution_freeze.py").read_bytes()
    ).hexdigest()
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(m))
    # Git's assume-unchanged flag hides a modified source file from status.
    target.write_text("raise RuntimeError('MALICIOUS_EXECUTED')\n")
    subprocess.run(
        ["git", "update-index", "--assume-unchanged",
         "src/sose/organizational/od5a_execution_freeze.py"],
        cwd=root, check=True,
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    for key in tuple(env):
        if key.startswith("COV_CORE_") or key == "COVERAGE_PROCESS_START":
            env.pop(key)
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-S",
         str(repo / "scripts/od5a_verify_execution_freeze.py"),
         "--root", str(root), "--manifest", str(manifest)],
        cwd=root, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "MALICIOUS_EXECUTED" not in result.stderr
    assert "tracked source" in result.stderr or "Git blob" in result.stderr


def test_bootstrap_refuses_nonisolated_python_before_shadowed_stdlib_import(tmp_path):
    """PYTHONPATH-provided argparse.py must never execute inside bootstrap."""
    import os
    from pathlib import Path
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[4]
    foreign = tmp_path / "untrusted"
    foreign.mkdir()
    (foreign / "argparse.py").write_text(
        "raise RuntimeError('SHADOW_ARGPARSE_EXECUTED')\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(foreign)
    for name in tuple(env):
        if name.startswith("COV_CORE_") or name == "COVERAGE_PROCESS_START":
            env.pop(name)
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts/od5a_verify_execution_freeze.py"),
         "--root", str(tmp_path), "--manifest", str(tmp_path / "missing.json")],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    assert "SHADOW_ARGPARSE_EXECUTED" not in proc.stderr
    assert "isolated" in proc.stderr.lower()


def test_bootstrap_must_reject_isolated_python_without_bytecode_flag(tmp_path):
    """Isolated -I alone is not equivalent to required interpreter-start -B."""
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[4]
    proc = subprocess.run(
        [sys.executable, "-I", "-S",
         str(repo / "scripts/od5a_verify_execution_freeze.py"),
         "--root", str(tmp_path), "--manifest", str(tmp_path / "missing.json")],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    assert "-B" in proc.stderr
    assert "isolated" in proc.stderr.lower()
