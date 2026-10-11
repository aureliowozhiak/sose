"""OD-1 accounting: immutable causes, actor development, and temporal config revisions."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sose.organizational.ledger import (
    ActorCategory,
    ActorLedger,
    ActorLedgerInterval,
    ItemCategory,
    ItemLedger,
    ItemLedgerInterval,
)
from sose.organizational.projection import (
    AccountingEvent,
    LedgerProjector,
    split_item_interval,
)


def _event(event_id, primary, start, end, cause, epoch=0, hash_="model-v1"):
    return AccountingEvent.item(
        event_id=event_id, work_item_id="task", start=start, end=end,
        category=primary, cause=cause, config_epoch=epoch,
        model_spec_hash=hash_,
    )


def test_winning_category_preserves_cause_and_rebuilds_without_loss():
    projector = LedgerProjector()
    projector.apply(_event("queue", ItemCategory.QUEUE, 0, 4, "queue-admission"))
    projector.apply(_event("doing", ItemCategory.PROCESSING, 2, 4, "execution-accepted"))
    observed = projector.item_ledger("task")
    assert [(x.start, x.end, x.primary, x.cause, x.config_epoch) for x in observed.intervals] == [
        (0, 2, ItemCategory.QUEUE, "queue-admission", 0),
        (2, 4, ItemCategory.PROCESSING, "execution-accepted", 0),
    ]
    observed.assert_complete(created_at=0, observed_at=4)
    state = projector.dump_state()
    assert LedgerProjector.from_state(state).dump_state() == state
    assert LedgerProjector.from_state(state).item_ledger("task") == observed
    assert observed.elapsed == 4


def test_contradictory_winning_causes_fail_closed_instead_of_choose_any():
    projector = LedgerProjector()
    projector.apply(_event("one", ItemCategory.PROCESSING, 0, 2, "decision-a"))
    projector.apply(_event("two", ItemCategory.PROCESSING, 1, 2, "decision-b"))
    with pytest.raises(ValueError, match="ambiguous causal provenance"):
        projector.item_ledger("task")


def test_overlapping_different_config_epochs_cannot_be_projected():
    projector = LedgerProjector()
    projector.apply(_event("one", ItemCategory.QUEUE, 0, 2, "a", 0, "m0"))
    projector.apply(_event("two", ItemCategory.PROCESSING, 1, 3, "b", 1, "m1"))
    with pytest.raises(ValueError, match="multiple model configurations|multiple config epochs"):
        projector.item_ledger("task")


def test_contiguous_config_epoch_advance_cannot_regress_or_rebind():
    good = ItemLedger(
        work_item_id="task",
        intervals=(
            ItemLedgerInterval(start=0, end=1, primary=ItemCategory.PROCESSING,
                               model_spec_hash="old", config_epoch=0),
            ItemLedgerInterval(start=1, end=2, primary=ItemCategory.PROCESSING,
                               model_spec_hash="new", config_epoch=1),
        ),
    )
    good.assert_complete(created_at=0, observed_at=2)
    with pytest.raises(ValidationError, match="config_epoch cannot regress"):
        ItemLedger(work_item_id="task", intervals=tuple(reversed((
            ItemLedgerInterval(start=1, end=2, primary=ItemCategory.PROCESSING,
                               model_spec_hash="old", config_epoch=0),
            ItemLedgerInterval(start=0, end=1, primary=ItemCategory.PROCESSING,
                               model_spec_hash="new", config_epoch=1),
        ))))
    with pytest.raises(ValidationError, match="same config_epoch"):
        ItemLedger(work_item_id="task", intervals=(
            ItemLedgerInterval(start=0, end=1, primary=ItemCategory.PROCESSING,
                               model_spec_hash="old", config_epoch=0),
            ItemLedgerInterval(start=1, end=2, primary=ItemCategory.PROCESSING,
                               model_spec_hash="new", config_epoch=0),
        ))


def test_development_costs_actor_time_but_never_double_allocates():
    projector = LedgerProjector()
    projector.apply(AccountingEvent.actor(
        event_id="training", actor_id="worker", start=0, end=2,
        category=ActorCategory.DEVELOPMENT, cause="training-program",
        model_spec_hash="m0", config_epoch=0,
    ))
    projector.apply(AccountingEvent.actor(
        event_id="work", actor_id="worker", start=2, end=3,
        category=ActorCategory.EXECUTION, work_item_id="task",
        cause="work-assigned", model_spec_hash="m0", config_epoch=0,
    ))
    ledger = projector.actor_ledger("worker")
    assert ledger.allocated_actor_time == 3
    assert ledger.duration_by_category()[ActorCategory.DEVELOPMENT] == 2
    assert ledger.intervals[0].cause == "training-program"
    assert LedgerProjector.from_state(projector.dump_state()).actor_ledger("worker") == ledger
    ledger.assert_complete(start=0, end=3)
    with pytest.raises(ValidationError, match="overlapping actor capacity"):
        ActorLedger(actor_id="worker", intervals=(
            ActorLedgerInterval(start=0, end=2, category=ActorCategory.DEVELOPMENT),
            ActorLedgerInterval(start=1, end=3, category=ActorCategory.EXECUTION),
        ))


def test_actor_epoch_overlap_or_regression_fails_closed():
    with pytest.raises(ValidationError, match="conflicting config epochs"):
        ActorLedger(actor_id="worker", fractional_multitasking=True, intervals=(
            ActorLedgerInterval(start=0, end=2, category=ActorCategory.DEVELOPMENT,
                                allocation=.4, config_epoch=0, model_spec_hash="m0"),
            ActorLedgerInterval(start=1, end=3, category=ActorCategory.EXECUTION,
                                allocation=.4, config_epoch=1, model_spec_hash="m1"),
        ))
    with pytest.raises(ValidationError, match="config_epoch cannot regress"):
        ActorLedger(actor_id="worker", intervals=(
            ActorLedgerInterval(start=0, end=1, category=ActorCategory.DEVELOPMENT,
                                config_epoch=2, model_spec_hash="m2"),
            ActorLedgerInterval(start=1, end=2, category=ActorCategory.EXECUTION,
                                config_epoch=1, model_spec_hash="m1"),
        ))


def test_nested_fractional_actor_epochs_reject_nonadjacent_conflict():
    # The long-lived reservation overlaps a later epoch even though the
    # neighboring short-lived interval ends before that epoch begins.
    with pytest.raises(ValidationError, match="conflicting config epochs"):
        ActorLedger(actor_id="worker", fractional_multitasking=True, intervals=(
            ActorLedgerInterval(start=0, end=10, category=ActorCategory.EXECUTION,
                                allocation=.25, config_epoch=0, model_spec_hash="m0"),
            ActorLedgerInterval(start=1, end=2, category=ActorCategory.DEVELOPMENT,
                                allocation=.25, config_epoch=0, model_spec_hash="m0"),
            ActorLedgerInterval(start=3, end=4, category=ActorCategory.COORDINATION,
                                allocation=.25, config_epoch=1, model_spec_hash="m1"),
        ))


def test_reused_actor_epoch_requires_one_unambiguous_model_hash():
    with pytest.raises(ValidationError, match="same actor config_epoch"):
        ActorLedger(actor_id="worker", intervals=(
            ActorLedgerInterval(start=0, end=1, category=ActorCategory.DEVELOPMENT,
                                config_epoch=0, model_spec_hash="m0"),
            ActorLedgerInterval(start=1, end=2, category=ActorCategory.EXECUTION,
                                config_epoch=0, model_spec_hash="different"),
        ))


def test_invalid_config_epoch_and_anonymous_version_fail():
    with pytest.raises(ValidationError, match="nonnegative integer"):
        _event("bad", ItemCategory.PROCESSING, 0, 1, "source", -1)
    with pytest.raises(ValidationError, match="model_spec_hash"):
        AccountingEvent.item(event_id="bad", work_item_id="task", start=0, end=1,
                             category=ItemCategory.QUEUE, config_epoch=0)
    with pytest.raises(ValidationError, match="nonempty"):
        _event("bad", ItemCategory.PROCESSING, 0, 1, "")


def test_split_uses_distinct_epochs_and_preserves_cause():
    original = ItemLedgerInterval(start=0, end=10, primary=ItemCategory.COORDINATION,
                                  cause="handoff", config_epoch=3, model_spec_hash="m3")
    before, after = split_item_interval(original, at=5,
                                        next_model_spec_hash="m4", next_config_epoch=4)
    assert (before.config_epoch, after.config_epoch) == (3, 4)
    assert before.cause == after.cause == "handoff"
    with pytest.raises(ValueError, match="advance config_epoch"):
        split_item_interval(original, at=5,
                            next_model_spec_hash="m3", next_config_epoch=3)


def test_preexisting_payloads_without_new_fields_remain_loadable():
    data = AccountingEvent.item(event_id="legacy", work_item_id="task",
                                start=0, end=2, category=ItemCategory.QUEUE)
    legacy = {key: value for key, value in data.model_dump(mode="json").items()
              if key not in ("cause", "config_epoch")}
    restored = LedgerProjector.from_state([legacy])
    interval = restored.item_ledger("task").intervals[0]
    assert interval.cause is None and interval.config_epoch is None
