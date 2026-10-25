"""#545 RED: public UoW predecessor forgery must not become trusted Engine evidence.

This test intentionally FAILS on vulnerable implementations. It is kept on a
test-only branch until native predecessor authority is implemented and checked.
Neither a correctly signed successor nor a deterministic event ID is evidence
that the preceding committed entity state was reached by a real StateChart.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sose.core.clock import SimulationClock
from sose.core.context import SimulationContext
from sose.core.engine import Engine
from sose.core.events import Command
from sose.core.randomness import RandomSource
from sose.core.scheduler import Scheduler
from sose.core.transition_authority import ATTESTATION_EVENT, TransitionAuthority
from sose.domain.registry import DomainRegistry, EntityType
from sose.examples.warehouse_fulfillment.entities import FulfillmentOrder
from sose.examples.warehouse_fulfillment.statecharts import FulfillmentOrderChart
from sose.persistence.memory import MemoryPersistence
from sose.persistence.sqlite import SQLitePersistence


OWNER = "warehouse:attested-prestate"
NOW = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
KEY = b"0123456789abcdef0123456789abcdef"


def _engine(store):
    registry = DomainRegistry()
    registry.register(EntityType("warehouse_fulfillment_order", FulfillmentOrderChart))
    context = SimulationContext(
        clock=SimulationClock(now=NOW, step=timedelta(seconds=1)),
        random=RandomSource(root_seed=17),
        scheduler=Scheduler(),
    )
    return Engine(
        persistence=store, owner_id=OWNER, registry=registry, context=context,
        transition_authority=TransitionAuthority("warehouse:issuer", "key:v1", KEY),
    )


@pytest.mark.parametrize("adapter", ("memory", "sqlite"))
def test_unsigned_public_prestate_cannot_be_laundered_by_real_engine_ship(adapter, tmp_path):
    """An attacker may write packed, but Engine must not certify a forged history."""
    path = tmp_path / "prestate-forgery.sqlite"
    store = MemoryPersistence() if adapter == "memory" else SQLitePersistence(path)
    order = FulfillmentOrder(
        id="order:forged-prestate", state="requested",
        created_at=NOW, updated_at=NOW,
    )
    try:
        with store.transaction(owner_id=OWNER) as uow:
            uow.save_entity(order)

        # Public writer forges the prerequisite packed state and plausible
        # version without executing allocate, start_pick, or pack.
        with store.transaction(owner_id=OWNER) as uow:
            tampered = uow.get_entity(order.entity_type, order.id)
            tampered.state = "packed"
            tampered.version = 3
            tampered.updated_at = NOW
            uow.save_entity(tampered)
        assert not [e for e in store.events() if e.name == ATTESTATION_EVENT]

        command = Command(
            command_id="cmd:ship-forged-prestate", name="ship",
            entity_type=order.entity_type, entity_id=order.id,
            owner_id=OWNER, due_at=NOW, issued_at=NOW,
            correlation_id="flow:forged-prestate",
        )
        with pytest.raises(ValueError, match="trusted predecessor|unauthenticated prestate"):
            _engine(store).dispatch(command)

        # Neither an untrusted packed state nor an untrusted predecessor
        # may induce an issuer-signed shipped state.
        assert store.entity(order.entity_type, order.id).state == "packed"
        assert not store.events()
    finally:
        if adapter == "sqlite":
            store.close()


@pytest.mark.parametrize("adapter", ("memory", "sqlite"))
def test_legitimate_four_step_warehouse_path_remains_attestable(adapter, tmp_path):
    """Positive control: independent source receipts may be verified after replay."""
    path = tmp_path / "prestate-genuine.sqlite"
    store = MemoryPersistence() if adapter == "memory" else SQLitePersistence(path)
    order = FulfillmentOrder(
        id="order:genuine", state="requested", created_at=NOW, updated_at=NOW,
    )
    try:
        with store.transaction(owner_id=OWNER) as uow:
            uow.save_entity(order)
        runtime = _engine(store)
        for step in ("allocate", "start_pick", "pack", "ship"):
            runtime.dispatch(Command(
                command_id=f"cmd:{step}-genuine", name=step,
                entity_type=order.entity_type, entity_id=order.id,
                owner_id=OWNER, due_at=NOW, issued_at=NOW,
                correlation_id="flow:genuine",
            ))
        sources = [e for e in store.events() if e.name == "entity.state_transition"]
        assert len(sources) == 4
        with store.transaction(owner_id=OWNER) as uow:
            authority = TransitionAuthority("warehouse:issuer", "key:v1", KEY)
            for source in sources:
                assert authority.verify(uow=uow, event=source).name == ATTESTATION_EVENT
        assert store.entity(order.entity_type, order.id).state == "shipped"
    finally:
        if adapter == "sqlite":
            store.close()
