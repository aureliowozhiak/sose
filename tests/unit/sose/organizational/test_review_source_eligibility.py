"""#564 O2: offline GitHub-shaped fixtures; not verified empirical observations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sose.organizational.dataset import ObservedPRDataset
from sose.organizational.github_observations import normalize_github_pr_trace
from sose.organizational.review_source_eligibility import (
    ReviewSourceEligibilityCriteria,
    evaluate_review_source_eligibility,
    has_source_paired_review,
)


UTC = timezone.utc
DAY0 = datetime(2026, 10, 10, tzinfo=UTC)


def _pr(index: int, *, timeline=(), reviews=()):
    start = DAY0 + timedelta(days=index)
    return normalize_github_pr_trace(
        repository="example/observable",
        pull_request={
            "number": index,
            "created_at": start.isoformat(),
            "merged_at": (start + timedelta(hours=4)).isoformat(),
        },
        timeline_events=timeline,
        reviews=reviews,
    )


def _request(i: int, actor: str | None, day: int, minute: int = 1, *, removed=False):
    record = {
        "id": i,
        "event": "review_request_removed" if removed else "review_requested",
        "created_at": (DAY0 + timedelta(days=day, minutes=minute)).isoformat(),
    }
    if actor is not None:
        record["requested_reviewer"] = {"login": actor}
    return record


def _review(i: int, actor: str | None, day: int, minute: int = 20):
    return {
        "id": i,
        "submitted_at": (DAY0 + timedelta(days=day, minutes=minute)).isoformat(),
        "state": "APPROVED",
        "user": {"login": actor} if actor is not None else None,
    }


def _dataset():
    return ObservedPRDataset(
        dataset_version="wave0-o2-fixture",
        traces=(
            _pr(1, timeline=(_request(11, "alice", 1),), reviews=(_review(21, "alice", 1),)),
            _pr(
                2,
                timeline=(_request(12, "bob", 2), _request(13, "bob", 2, 5, removed=True)),
                reviews=(_review(22, "bob", 2),),
            ),
            _pr(
                3,
                timeline=(
                    _request(14, "carol", 3),
                    _request(15, "carol", 3, 5, removed=True),
                    _request(16, "carol", 3, 7),
                ),
                reviews=(_review(23, "carol", 3, 20),),
            ),
            _pr(4, timeline=(_request(17, "dan", 4),), reviews=(_review(24, "dan", 4),)),
        ),
    )


def _criteria(*, threshold=0.5, min_count=2):
    return ReviewSourceEligibilityCriteria(
        registration_source="https://example.org/immutable/criteria-before-2026-10-10",
        registered_at=datetime(2026, 9, 30, tzinfo=UTC),
        min_train_pr_count=min_count,
        min_paired_review_pr_fraction=threshold,
        holdout_fraction=0.25,
    )


def _assess(dataset, criteria):
    return evaluate_review_source_eligibility(
        dataset,
        criteria=criteria,
        registered_criteria_hash=criteria.criteria_hash,
        expected_dataset_hash=dataset.dataset_hash,
    )


def test_source_paired_review_coverage_is_not_ci_gate_coverage_or_actor_time():
    dataset, criteria = _dataset(), _criteria()
    report = _assess(dataset, criteria)
    assert report.train_pr_count == 3
    assert report.paired_review_pr_count == 2
    assert report.paired_review_pr_fraction == pytest.approx(2 / 3)
    assert report.holdout_pr_count == 1
    assert report.purged_pr_count == 0
    assert report.failed_requirements == ()
    assert report.source_observability_eligible
    assert not hasattr(report, "reviewer_service_hours")
    assert not hasattr(report, "scientific_admitted")


def test_heldout_only_pair_cannot_make_training_eligible():
    dataset = _dataset()
    traces = list(dataset.traces)
    traces[0] = _pr(1)
    traces[2] = _pr(3)
    changed = ObservedPRDataset(dataset_version=dataset.dataset_version, traces=tuple(traces))
    report = _assess(changed, _criteria())
    assert report.paired_review_pr_count == 0
    assert report.holdout_pr_count == 1
    assert not report.source_observability_eligible
    assert report.failed_requirements == ("min_paired_review_pr_fraction",)


def test_removed_requests_and_re_requests_do_not_pair_with_old_request():
    dataset = _dataset()
    assert has_source_paired_review(dataset.traces[0])
    assert not has_source_paired_review(dataset.traces[1])
    assert has_source_paired_review(dataset.traces[2])


def test_team_and_anonymous_requests_never_create_individual_pair():
    team = _pr(
        1,
        timeline=({
            "id": 101,
            "event": "review_requested",
            "created_at": (DAY0 + timedelta(days=1, minutes=1)).isoformat(),
            "requested_team": {"slug": "core"},
        },),
        reviews=(_review(102, "alice", 1),),
    )
    anonymous = _pr(
        2,
        timeline=(_request(103, None, 2),),
        reviews=(_review(104, "bob", 2),),
    )
    assert not has_source_paired_review(team)
    assert not has_source_paired_review(anonymous)


def test_corrupted_source_identity_fails_closed():
    original = _dataset().traces[0]
    events = list(original.events)
    idx = next(i for i, ev in enumerate(events) if ev.kind.value == "review_submitted")
    events[idx] = events[idx].model_copy(update={"source_event_id": "untrusted:review:21"})
    changed = original.model_copy(update={"events": tuple(events)})
    with pytest.raises(ValueError, match="GitHub source identity"):
        has_source_paired_review(changed)


def test_duplicate_event_source_id_is_rejected_at_ingestion():
    with pytest.raises(ValueError, match="duplicate source_event_id"):
        _pr(
            1,
            timeline=(_request(11, "alice", 1),),
            reviews=(_review(21, "alice", 1), _review(21, "alice", 1, 25)),
        )


def test_criteria_hash_and_dataset_hash_must_match_precommitted_values():
    dataset, criteria = _dataset(), _criteria()
    with pytest.raises(ValueError, match="criteria hash"):
        evaluate_review_source_eligibility(
            dataset, criteria=criteria, registered_criteria_hash="f" * 64,
            expected_dataset_hash=dataset.dataset_hash,
        )
    with pytest.raises(ValueError, match="dataset hash"):
        evaluate_review_source_eligibility(
            dataset, criteria=criteria, registered_criteria_hash=criteria.criteria_hash,
            expected_dataset_hash="e" * 64,
        )


def test_retrospective_registration_and_invalid_criteria_rejected():
    dataset = _dataset()
    criteria = _criteria().model_copy(update={"registered_at": DAY0 + timedelta(days=10)})
    with pytest.raises(ValueError, match="postdates source cohort"):
        _assess(dataset, criteria)
    with pytest.raises(ValidationError):
        _criteria(threshold=1.01)
    with pytest.raises(ValidationError):
        _criteria(threshold=0.0)


def test_minimum_train_cohort_is_checked_independently_of_review_fraction():
    report = _assess(_dataset(), _criteria(min_count=4))
    assert not report.source_observability_eligible
    assert report.failed_requirements == ("min_train_pr_count",)


def test_source_event_reused_across_different_prs_fails_closed_even_if_hash_pinned():
    dataset = _dataset()
    first = dataset.traces[0]
    second = dataset.traces[1]
    first_request = next(
        ev for ev in first.events if ev.kind.value == "review_requested"
    )
    changed_events = tuple(
        ev.model_copy(update={"source_event_id": first_request.source_event_id})
        if ev.kind.value == "review_requested"
        else ev
        for ev in second.events
    )
    forged_second = second.model_copy(update={"events": changed_events})
    forged = ObservedPRDataset(
        dataset_version="forged-frozen-but-corrupt",
        traces=(first, forged_second, *dataset.traces[2:]),
    )
    with pytest.raises(ValueError, match="reused across pull requests"):
        _assess(forged, _criteria())
