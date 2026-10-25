"""#477 five-arm PostgreSQL-native vs reducer/reopened source + physical parity.

Non-confirmatory bounded differential; NOT network-partition, fairness or DOE.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from sose.core.identity import deterministic_id
from sose.organizational.od5a_durable import (
    advance_od5a_durable, initialize_od5a_durable,
    od5a_durable_events, od5a_durable_state,
)
from sose.organizational.od5a_mechanisms import OD5aWorkItem
from sose.organizational.od5a_recurring import (
    SharedPhysicalPoolBinding, initialize_od5a_recurring_job,
    run_od5a_recurring_tick,
)
from sose.persistence.postgres import PostgresPersistence
from sose.persistence.sqlite import SQLitePersistence
from tests.e2e.sose.persistence.test_postgres_od5a_shared_native_physical_authority import _pool
from tests.integration.sose.organizational.test_od5a_recurring_simpy import _arms

DSN = os.environ.get("SOSE_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="real PostgreSQL required")
ARM_NAMES = (
    "baseline", "capacity_only", "topology_only",
    "coordination_only", "structural_combined",
)
WALL = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)


def _physical_truth(store):
    physical = store.temporal_resources()
    assert physical.audit()
    reservations = physical.reservations()
    assert all(r.units > 0 and r.start_at < r.end_at for r in reservations)
    for i, first in enumerate(reservations):
        for second in reservations[i + 1:]:
            if first.address != second.address:
                continue
            left_end = first.stopped_at or first.end_at
            right_end = second.stopped_at or second.end_at
            assert left_end <= second.start_at or right_end <= first.start_at, (
                first, second,
            )
    return reservations


def _source_truth(store, org):
    return (
        od5a_durable_state(store, job_id=org),
        od5a_durable_events(store, job_id=org),
        store.resource_demands(),
        store.resource_reservations(),
        store.resource_release_intents(),
        store.resource_definitions(),
    )


def _step(store, org, binding, ordinal):
    return run_od5a_recurring_tick(
        store, job_id=org, owner_id="worker:" + org,
        now=WALL + timedelta(seconds=ordinal),
        lease_duration=timedelta(seconds=60),
        trigger_id=deterministic_id(
            "od5a-recurring-tick", org, store.job_state(org).run_count + 1,
        ),
        shared_pool_binding=binding,
    )


@pytest.mark.parametrize("arm_name", ARM_NAMES)
def test_pg_native_and_reopened_physical_traces_match_sqlite_reducer_every_step(
    tmp_path, arm_name,
):
    """Every native PostgreSQL step matches independently reduced semantics."""
    assert DSN is not None
    arm = _arms()[arm_name]
    org = "org:five-arm-check"
    items = (OD5aWorkItem(
        "item:same-exogenous", 0.0,
        (("a", 0.2), ("b", 0.2), ("c", 0.1)),
    ),)
    slots = arm.model.parameters["execution_slots"]
    assert type(slots) is int and 1 <= slots <= 2
    binding = SharedPhysicalPoolBinding(
        pool=_pool(),
        execution_instances=tuple(
            (f"execution:{i}", f"unit-{i + 1}") for i in range(slots)
        ),
    )
    prefix = "od5a_5arm_pg_" + uuid4().hex[:12]
    steady_ns, reopened_ns = prefix + "_steady", prefix + "_again"
    reference_path = tmp_path / f"{arm_name}_reference.sqlite"
    with SQLitePersistence(reference_path) as reference:
        initialize_od5a_durable(reference, job_id=org, arm=arm, items=items)
    for namespace in (steady_ns, reopened_ns):
        with PostgresPersistence(DSN, namespace=namespace) as pg:
            initialize_od5a_recurring_job(
                pg, job_id=org, arm=arm, items=items,
                shared_pool_binding=binding,
            )
    completed = False
    with (
        SQLitePersistence(reference_path) as reference,
        PostgresPersistence(DSN, namespace=steady_ns) as steady,
    ):
        for tick in range(75):
            reference_advanced = advance_od5a_durable(reference, job_id=org)
            steady_result = _step(steady, org, binding, tick)
            with PostgresPersistence(DSN, namespace=reopened_ns) as restarted:
                restart_result = _step(restarted, org, binding, tick)
                assert restart_result.action == steady_result.action
                assert _source_truth(steady, org) == _source_truth(reference, org)
                assert _source_truth(restarted, org) == _source_truth(reference, org)
                assert _physical_truth(steady) == _physical_truth(restarted)
                for booked in _physical_truth(restarted):
                    assert booked.owner_id == org
                    assert booked.address.instance_id in {"unit-1", "unit-2"}
                    assert booked.causation_id in {
                        e.event_id for e in restarted.events() if e.owner_id == org
                    }
                assert restarted.job_state(org).run_count == steady.job_state(org).run_count
                assert restarted.job_state(org).next_tick == steady.job_state(org).next_tick
                assert restart_result.action == (
                    "advanced" if reference_advanced else "complete"
                )
            if steady_result.action == "complete":
                assert od5a_durable_state(reference, job_id=org)["done"]
                completed = True
                break
    assert completed, f"{arm_name} did not finish bounded 3-way PG native trace"
