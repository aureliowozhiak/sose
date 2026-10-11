"""Fail-closed checks for the OD-5a design registration, not an executed freeze."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("docs/organizational/preregistration/od5a-structure-capacity-v2-design.json")


def _design() -> dict:
    return json.loads(ROOT.read_text(encoding="utf-8"))


def test_od5a_design_has_finite_arms_comparators_and_no_confirmatory_execution() -> None:
    plan = _design()
    assert plan["protocol_id"] == "od5a-structure-capacity-v2"
    assert plan["stage"] == "design_preregistration"
    assert plan["status"] == "draft_no_confirmatory_execution"
    assert plan["primary_arms"] == [
        "baseline", "capacity_only", "topology_only",
        "coordination_only", "structural_combined",
    ]
    assert plan["eligible_pairwise_contrasts"] == [
        f"{arm}:capacity_only"
        for arm in ("topology_only", "coordination_only", "structural_combined")
    ]
    assert plan["cost_matching"]["baseline_matched"] is False
    assert plan["cost_matching"]["budget_tolerance_fraction"] == 0.01
    assert plan["cost_matching"]["unpriced_transition_permitted"] is False
    assert plan["primary"]["practical_improvement_fraction"] == -0.05
    assert plan["primary"]["throughput_ratio_minimum"] == 0.98
    assert plan["analysis"]["multiplicity"].startswith("Holm")


def test_od5a_prospective_regimes_do_not_depend_on_post_treatment_outcomes() -> None:
    plan = _design()
    regimes = set(plan["exogenous_coordinates"])
    assert "rho_nominal" in regimes
    assert not regimes.intersection(plan["forbidden_regime_coordinates"])
    assert plan["break_even"]["coordinate"] == "configured rho_nominal"
    assert plan["break_even"]["no_root"] == "nonexistent"
    assert plan["break_even"]["multiple_roots"] == "nonunique_report_all"
    assert plan["break_even"]["do_not_use_realized_regime_coords"] is True
    assert plan["analysis"]["report_all_null_regions"] is True
    assert plan["analysis"]["report_harmful_regions"] is True


def test_od5a_cannot_be_accepted_as_execution_freeze_with_missing_commitments() -> None:
    plan = _design()
    assert plan["allocation"]["design"] == "sobol"
    assert plan["allocation"]["n_worlds"] == 64
    assert plan["allocation"]["replications_per_world_arm"] == 16
    for key in ("root_seed", "bounds", "fixed_horizon"):
        assert plan["allocation"][key] == "UNSET_AT_EXECUTION_FREEZE"
    assert len(plan["execution_freeze_prerequisites"]) >= 8
    assert set(plan["evidence_policy"]["never_modify"]) == {
        "manufacturing_v1", "o2c_v1", "mro_v1", "pr_review_validation_v1",
    }
    assert {"cause", "config_epoch", "model_spec_hash"} <= set(
        plan["evidence_policy"]["provenance"]
    )
