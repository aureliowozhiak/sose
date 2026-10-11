"""Atomic publication-to-trigger accounting for interrupted PC6 recurrences."""
from datetime import datetime, timezone
from dataclasses import replace

import pytest

from sose.composition.boundary import BoundaryService
from sose.composition.model import BoundaryMessage
from sose.jobs.model import SimulationJobState
from sose.persistence.memory import MemoryPersistence


def _message():
    return BoundaryMessage.create(
        contract_name="logistics.delivery_completed",
        contract_version=1,
        source_domain="logistics",
        source_identity="shipment-1",
        destination_domain="order_to_cash",
        occurrence_key="delivery-completed",
        correlation_id="customer-1",
        causation_id=None,
        produced_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        payload={"shipment_id": "shipment-1", "order_id": "sales-1"},
    )


def _job():
    return SimulationJobState(
        job_id="recurring-pc6", domain_name="trading_company_composition",
        config_json="{}", config_revision=1, status="running",
        initialized=True, logical_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
        next_tick=0, active_trigger_id="recurring-slot-0",
    )


def test_recovery_publication_enrollment_commits_with_message_and_is_idempotent():
    store = MemoryPersistence()
    with store.transaction() as uow:
        uow.save_job_state(_job())
    message = _message()
    delivery = BoundaryService(store).publish(
        message, recovery_job_id="recurring-pc6",
    )
    assert delivery.message_id == message.message_id
    assert store.job_state("recurring-pc6").active_publication_message_ids == (
        message.message_id,
    )
    assert BoundaryService(store).publish(
        message, recovery_job_id="recurring-pc6",
    ) == delivery
    assert store.job_state("recurring-pc6").active_publication_message_ids == (
        message.message_id,
    )


@pytest.mark.parametrize("kind", ("missing_job", "completed_job"))
def test_publication_refuses_missing_or_completed_recurring_trigger_atomically(kind):
    store = MemoryPersistence()
    if kind == "completed_job":
        with store.transaction() as uow:
            uow.save_job_state(replace(_job(), active_trigger_id=None, status="ready"))
    message = _message()
    with pytest.raises(RuntimeError, match="active recurring trigger"):
        BoundaryService(store).publish(
            message, recovery_job_id="recurring-pc6",
        )
    with store.transaction() as uow:
        assert uow.get_boundary_message(message.message_id) is None
        assert uow.get_boundary_delivery(
            __import__("sose.composition.model", fromlist=["BoundaryDelivery"]).
            BoundaryDelivery.pending(message).delivery_id
        ) is None


def test_publication_identity_cannot_be_enrolled_without_its_message():
    store = MemoryPersistence()
    message = _message()
    with store.transaction() as uow:
        uow.save_job_state(replace(
            _job(), active_publication_message_ids=(message.message_id,),
        ))
    with pytest.raises(RuntimeError, match="enrolled recovery publication"):
        BoundaryService(store).publish(message, recovery_job_id="recurring-pc6")


def test_publication_enrollment_rejects_duplicate_or_empty_identities():
    with pytest.raises(ValueError, match="unique nonempty"):
        replace(_job(), active_publication_message_ids=("same", "same"))
    with pytest.raises(ValueError, match="unique nonempty"):
        replace(_job(), active_publication_message_ids=("",))
