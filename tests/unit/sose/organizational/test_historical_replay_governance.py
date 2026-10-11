"""OD-0 scientific freeze governance tests: fail closed without modifying v1 evidence."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts.verify_organizational_v1_replay_contract import (
    APPROVED,
    APPROVED_PUBLISHED_BLOB,
    CANONICAL,
    FREEZES,
    PUBLISHED_PATH,
    WORKFLOW_PATH,
    git_blob,
    verify_governance,
    verify_manifests,
    verify_registry,
    verify_workflow,
)


@pytest.fixture
def freeze_root(tmp_path: Path) -> Path:
    """Copy only governance input files so tampering never modifies real freezes."""
    source = Path.cwd()
    for path in (PUBLISHED_PATH, WORKFLOW_PATH, *(path for path, _ in FREEZES.values())):
        path = Path(path)
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, target)
    return tmp_path


def test_git_blob_uses_git_header_not_raw_content_hash() -> None:
    assert git_blob(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert git_blob(b"a") != git_blob(b"b")


def test_reviewed_v1_inventory_replays_historical_source_not_current_head(
    freeze_root: Path,
) -> None:
    report = verify_governance(freeze_root)
    assert report["status"] == "pinned-source-and-released-digests-verified"
    assert report["registry_blob"] == APPROVED_PUBLISHED_BLOB
    assert report["domains"] == sorted(APPROVED)
    registry = verify_registry(freeze_root)
    assert all(set(entry["canonical_files"]) == CANONICAL for entry in registry.values())
    verify_manifests(freeze_root)
    verify_workflow(freeze_root, registry)


def test_replacing_one_published_file_digest_fails_before_replay(freeze_root: Path) -> None:
    path = freeze_root / PUBLISHED_PATH
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["mro"]["canonical_files"]["runs.json"] = "f" * 64
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ValueError, match="trusted published file digests"):
        verify_governance(freeze_root)


def test_replacing_published_source_to_match_a_modified_workflow_still_fails(
    freeze_root: Path,
) -> None:
    registry_path = freeze_root / PUBLISHED_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["o2c"]["source_sha"] = "0" * 40
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    workflow_path = freeze_root / WORKFLOW_PATH
    workflow = yaml.load(workflow_path.read_text(), Loader=yaml.BaseLoader)
    workflow["jobs"]["replay-historical-v1"]["strategy"]["matrix"]["include"][1][
        "source_sha"
    ] = "0" * 40
    workflow_path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(ValueError, match="trusted published file digests"):
        verify_governance(freeze_root)


@pytest.mark.parametrize("domain", sorted(FREEZES))
def test_mutating_any_v1_preregistration_blob_fails_closed(
    freeze_root: Path, domain: str,
) -> None:
    path = freeze_root / FREEZES[domain][0]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["official_execution_performed"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="immutable preregistration blob"):
        verify_governance(freeze_root)


def test_workflow_must_not_checkout_development_main(freeze_root: Path) -> None:
    path = freeze_root / WORKFLOW_PATH
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    checkout = next(
        step for step in workflow["jobs"]["replay-historical-v1"]["steps"]
        if step.get("name") == "Checkout exact historical scientific source"
    )
    checkout["with"]["ref"] = "main"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(ValueError, match="not pinned to source SHA"):
        verify_governance(freeze_root)


def test_workflow_rejects_retargeting_of_result_hash(freeze_root: Path) -> None:
    path = freeze_root / WORKFLOW_PATH
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    workflow["jobs"]["replay-historical-v1"]["strategy"]["matrix"]["include"][0][
        "result_sha"
    ] = "0" * 64
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(ValueError, match="historical replay identity"):
        verify_governance(freeze_root)


def test_workflow_rejects_dropping_independent_canonical_digest_check(
    freeze_root: Path,
) -> None:
    path = freeze_root / WORKFLOW_PATH
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    proof = next(
        step for step in workflow["jobs"]["replay-historical-v1"]["steps"]
        if step.get("name") == "Independently verify canonical historical result and file digests"
    )
    proof["run"] = proof["run"].replace(
        "actual_digest == expected_digest", "True"
    )
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(ValueError, match="independent file-digest verification"):
        verify_governance(freeze_root)


def test_workflow_checks_governance_changes_and_preserves_failure_staging(
    freeze_root: Path,
) -> None:
    path = freeze_root / WORKFLOW_PATH
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    workflow["on"]["pull_request"]["paths"].remove(
        "docs/architecture/decisions/adr-0007-versioned-scientific-freezes.md"
    )
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(ValueError, match="not triggered by governance edits"):
        verify_governance(freeze_root)


def test_workflow_must_run_current_governance_check_before_historical_execution(
    freeze_root: Path,
) -> None:
    path = freeze_root / WORKFLOW_PATH
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["replay-historical-v1"]
    job["steps"] = [
        step for step in job["steps"]
        if step.get("name") != "Verify immutable historical freeze governance"
    ]
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required replay step"):
        verify_governance(freeze_root)
