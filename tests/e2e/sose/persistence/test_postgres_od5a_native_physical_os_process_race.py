"""#477: two independent PostgreSQL OS workers cannot grant one physical unit twice.

This is a bounded native-grant arbitration falsifier, NOT five-arm scientific
equivalence, server/network failure certification, or full durable fairness.
"""
from __future__ import annotations

import os
from multiprocessing import get_context
from uuid import uuid4

import pytest

from sose.organizational import od5a_recurring
from sose.persistence.postgres import PostgresPersistence
from tests.e2e.sose.persistence.test_postgres_od5a_shared_native_physical_authority import (
    _binding, _seed, _source, _tick,
)

DSN = os.environ.get("SOSE_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="live SOSE_TEST_POSTGRES_DSN required")


def _separate_owner(dsn, namespace, org, barrier, answers):
    """A fresh Python interpreter and fresh PG connection for each owner."""
    original = od5a_recurring._RecurringNativePhysicalArbiter.prepare

    def meet_at_native_grant(self, *, releases, grants, at):
        original(self, releases=releases, grants=grants, at=at)
        if grants and self.execution_pool == f"{org}/execution-pool":
            barrier.wait(timeout=30)

    od5a_recurring._RecurringNativePhysicalArbiter.prepare = meet_at_native_grant
    try:
        with PostgresPersistence(dsn, namespace=namespace) as store:
            action = _tick(store, org, _binding("unit-1")).action
            answers.put((org, action))
    except BaseException as exc:
        answers.put((org, f"ERROR: {type(exc).__name__}: {exc}"))
        raise


def test_pg_independent_os_processes_cannot_commit_same_native_unit_twice():
    """Both workers observe a native SimPy grant before either DB arbiter commits.

    Only the shared PostgreSQL physical authority may decide the winner; a
    second speculative native grant must downgrade to durable waiting with no
    committed source effect. No cross-owner process-local lock is sufficient.
    """
    assert DSN is not None
    namespace = "od5a_os_physical_" + uuid4().hex[:12]
    owners = ("org:os-one", "org:os-two")
    binding = _binding("unit-1")
    with PostgresPersistence(DSN, namespace=namespace) as seed:
        for org in owners:
            _seed(seed, org, binding)

    ctx = get_context("spawn")
    barrier = ctx.Barrier(2)
    answers = ctx.Queue()
    workers = [
        ctx.Process(
            target=_separate_owner,
            args=(DSN, namespace, org, barrier, answers),
            name=f"od5a-{org}",
        )
        for org in owners
    ]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=65)
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=10)
        assert all(worker.exitcode == 0 for worker in workers), [
            (worker.name, worker.exitcode) for worker in workers
        ]
        results = dict(answers.get(timeout=10) for _ in owners)
        assert set(results) == set(owners)
        assert sorted(results.values()) == ["advanced", "waiting"], results
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=10)
            worker.close()
        answers.close()
        answers.join_thread()

    winner = next(org for org, action in results.items() if action == "advanced")
    loser = next(org for org, action in results.items() if action == "waiting")
    with PostgresPersistence(DSN, namespace=namespace) as reopened:
        physical = reopened.temporal_resources()
        bookings = physical.reservations()
        assert len(bookings) == 1
        assert bookings[0].owner_id == winner
        assert bookings[0].address.instance_id == "unit-1"
        assert _source(reopened, winner)["step"] == 1
        assert _source(reopened, loser)["step"] == 0
        assert not any(event.owner_id == loser for event in reopened.events())
        assert reopened.job_state(loser).run_count == 0
        assert physical.audit()
