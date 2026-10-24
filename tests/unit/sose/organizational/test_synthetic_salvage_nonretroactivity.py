"""#565 S1: prevent retroactive synthetic reference-v1 criteria promotion."""
from __future__ import annotations

import json
from pathlib import Path

from sose.organizational.synthetic_analysis import SyntheticRecoveryReport
from sose.organizational.synthetic_reference_experiment import (
    REFERENCE_DESIGN_SEED_V1,
    REFERENCE_ROOT_SEED_V1,
    build_reference_synthetic_experiment_v1,
)


_ROOT = Path(__file__).resolve().parents[4]
_PUBLISHED = _ROOT / "docs/organizational/evidence/synthetic-reference-v1"


def test_published_reference_v1_keeps_original_design_seeds_arms_and_replications():
    design = build_reference_synthetic_experiment_v1()
    protocol = json.loads((_PUBLISHED / "protocol.json").read_text(encoding="utf-8"))
    assert REFERENCE_DESIGN_SEED_V1 == REFERENCE_ROOT_SEED_V1 == 20261007
    assert design.design_seed == design.root_seed == 20261007
    assert design.protocol.sample_size == protocol["sample_size"] == 12
    assert design.protocol.replication_plan.min_replications == 16
    assert design.protocol.replication_plan.max_replications == 16
    assert set(protocol["intervention_ids"]) == {"capacity-up", "automation-rework"}
    assert len(design.worlds) == 36


def test_orphan_thresholds_are_not_preregistered_in_frozen_reference_v1():
    protocol = json.loads((_PUBLISHED / "protocol.json").read_text(encoding="utf-8"))
    published = json.loads((_PUBLISHED / "report.json").read_text(encoding="utf-8"))
    for orphan_key in ("max_mean_relative_error_stable", "min_direction_recovery_rate"):
        assert orphan_key not in protocol
        assert orphan_key not in published
    assert "mean_relative_error_stable" in published
    assert "direction_recovery_rate" in published


def test_archived_v1_manifest_keeps_published_protocol_report_identity():
    manifest = json.loads((_PUBLISHED / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "synthetic-reference-experiment/v1"
    assert manifest["protocol_sha256"] == (
        "b9af4b62e225584375ae48cb1432029c6031ca509a98c0ae8e29d2e5e8c8f87c"
    )
    assert manifest["report_sha256"] == (
        "428245d1eeb849dc1a9f5a333f92032d3a76c55ed3254ba6e4b51cad2fe7d086"
    )


def test_empty_regimes_and_unidentified_directions_are_not_self_certifying():
    # Structural report validity is not a prospective verifier admission.
    report = SyntheticRecoveryReport(
        protocol_hash="a" * 64,
        dataset_hash="b" * 64,
        world_count=1,
        stable_world_count=0,
        saturated_world_count=0,
        mean_relative_error_stable=0.0,
        direction_recovery_rate=0.0,
        worlds=(),
        effects=(),
    )
    assert report.stable_world_count == 0
    assert report.saturated_world_count == 0
    assert report.direction_recovery_rate == 0.0
    assert not hasattr(report, "criteria_hash")
    assert not hasattr(report, "scientific_admitted")
