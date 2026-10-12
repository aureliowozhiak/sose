"""Restartable OD-5a boundary reconciler under real independent OS-worker deaths.

Validates the operational boundary *after* durable source-event production.
Not a SimPy production runner, multi-node fencing certificate or OD-5a DOE.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from multiprocessing import get_context

import pytest

from sose.core.identity import deterministic_id
from sose.organizational.model_spec import EvidenceClass, ModelSpec
from sose.organizational.od5a_admission import OD5aChargedCost, compile_od5a_arms
from sose.organizational.od5a_durable import (
    advance_od5a_durable, initialize_od5a_durable, od5a_durable_events,
)
from sose.organizational.od5a_mechanisms import OD5aWorkItem
from sose.organizational.od5a_reconciler import reconcile_od5a_boundary_once
from sose.persistence.sqlite import SQLitePersistence


NOW = datetime(2000, 1, 2, tzinfo=timezone.utc)
LEASE = timedelta(minutes=30)
PHASES = ("published", "claimed", "acknowledged", "applied", "certified")


def _arms():
    model = ModelSpec(
        stations={"a": {}, "b": {}, "c": {}},
        routing={"dependency_edges": [["a", "b"], ["b", "c"]]},
        demand={"arrival_process": "exogenous"},
        parameters={
            "arrival_rate": 0.8, "execution_slots": 1,
            "coordination_latency": 0.1, "service_cv": 0.5,
        },
        parameter_evidence={
            x: EvidenceClass.ASSUMED for x in (
                "arrival_rate", "execution_slots", "coordination_latency", "service_cv",
            )
        },
    )
    return {x.arm_id: x for x in compile_od5a_arms(
        baseline=model, expanded_capacity=2,
        removed_dependency_edges=(("a", "b"),),
        reduced_coordination_latency=0.05,
        declared_costs={
            x: OD5aChargedCost(8, 1, 1, 1) for x in (
                "capacity_only", "topology_only", "coordination_only",
                "structural_combined",
            )
        },
    )}


def _seed(path, jobs):
    with SQLitePersistence(path) as store:
        for job, arm in jobs.items():
            initialize_od5a_durable(
                store, job_id=job, arm=_arms()[arm],
                items=(OD5aWorkItem(
                    "item:" + job, 0.0,
                    (("a", 0.2), ("b", 0.3), ("c", 0.1)),
                ),),
            )
        for job in jobs:
            for _ in range(80):
                if not advance_od5a_durable(store, job_id=job):
                    break
            else:
                raise AssertionError("physical source did not finish")
            assert any(e.payload["kind"] == "execution"
                       for e in od5a_durable_events(store, job_id=job))
        assert not store.resource_reservations()


def _drive(path, job, *, owner=None, at=NOW):
    with SQLitePersistence(path) as store:
        history = []
        for _ in range(500):
            step = reconcile_od5a_boundary_once(
                store, job_id=job, owner_id=owner or "worker:" + job,
                now=at, lease_duration=LEASE,
            )
            history.append(step.phase)
            if step.phase == "idle":
                return tuple(history)
            if step.phase == "blocked":
                raise AssertionError("uncontended single-worker run became blocked")
        raise AssertionError("reconciliation did not terminate")


def _snapshot(path, jobs):
    with SQLitePersistence(path) as store:
        events = tuple(sorted(store.events(), key=lambda x: x.event_id))
        definitions = tuple(sorted(store.resource_definitions(), key=lambda x: x.name))
        reservations = tuple(sorted(store.resource_reservations(), key=lambda x: x.reservation_id))
        with store.transaction() as uow:
            deliveries = tuple(sorted(uow.boundary_deliveries(), key=lambda d: d.delivery_id))
            messages = tuple(uow.get_boundary_message(d.message_id) for d in deliveries)
            consumptions = tuple(uow.get_boundary_consumption(d.delivery_id) for d in deliveries)
            observations = tuple(
                uow.get_entity("od5a_physical_observation", e.event_id)
                for e in events if e.name in {"od5a.execution.v1", "od5a.coordination.v1"}
            )
            commands = tuple(
                uow.get_command(d.consumer_effect_id)
                for d in deliveries if d.consumer_effect_id is not None
            )
            return {
                "events": events,
                "source_entities": tuple(
                    uow.get_entity("od5a_durable_pilot", j) for j in sorted(jobs)
                ),
                "definitions": definitions, "reservations": reservations,
                "messages": messages, "deliveries": deliveries,
                "consumptions": consumptions,
                "observations": observations, "commands": commands,
                "certificates": uow.business_effects(),
            }


def _exit_after_one_committed_step(path, job, owner, at, phase):
    import os

    with SQLitePersistence(path) as store:
        result = reconcile_od5a_boundary_once(
            store, job_id=job, owner_id=owner, now=at,
            lease_duration=LEASE,
        )
        assert result.phase == phase, (result.phase, phase)
        os._exit(97)


def _spawn_and_die(path, job, owner, at, phase):
    ctx = get_context("spawn")
    child = ctx.Process(
        target=_exit_after_one_committed_step,
        args=(str(path), job, owner, at, phase),
    )
    child.start()
    child.join(timeout=30)
    if child.is_alive():
        child.kill()
        child.join()
        pytest.fail("reconciliation worker hung")
    assert child.exitcode == 97, f"worker exited unexpectedly: {child.exitcode}"


@pytest.mark.parametrize("arm", [
    "baseline", "capacity_only", "topology_only",
    "coordination_only", "structural_combined",
])
@pytest.mark.parametrize("death_phase", PHASES)
def test_kill_after_each_committed_boundary_phase_reconstructs_full_truth(
    tmp_path, arm, death_phase,
):
    jobs = {"org:alpha": arm}
    control, killed = tmp_path / "control.db", tmp_path / "killed.db"
    _seed(control, jobs)
    _seed(killed, jobs)
    reference_steps = _drive(control, "org:alpha")
    assert all(p in reference_steps for p in PHASES)
    with SQLitePersistence(killed) as store:
        for earlier in PHASES[:PHASES.index(death_phase)]:
            result = reconcile_od5a_boundary_once(
                store, job_id="org:alpha", owner_id="worker:org:alpha",
                now=NOW, lease_duration=LEASE,
            )
            assert result.phase == earlier
    _spawn_and_die(killed, "org:alpha", "worker:org:alpha", NOW, death_phase)
    _drive(killed, "org:alpha")
    assert _snapshot(killed, jobs) == _snapshot(control, jobs)


def test_killed_owner_claim_blocks_until_lease_expiry_then_fences_recovery(tmp_path):
    jobs = {"org:alpha": "baseline"}
    control, killed = tmp_path / "control.db", tmp_path / "killed.db"
    _seed(control, jobs)
    _seed(killed, jobs)

    for path in (control, killed):
        with SQLitePersistence(path) as store:
            first = reconcile_od5a_boundary_once(
                store, job_id="org:alpha", owner_id="old",
                now=NOW, lease_duration=LEASE,
            )
            assert first.phase == "published"
    with SQLitePersistence(control) as store:
        claim = reconcile_od5a_boundary_once(
            store, job_id="org:alpha", owner_id="old",
            now=NOW, lease_duration=LEASE,
        )
        assert claim.phase == "claimed"
    _spawn_and_die(killed, "org:alpha", "old", NOW, "claimed")

    for path in (control, killed):
        with SQLitePersistence(path) as store:
            blocked = reconcile_od5a_boundary_once(
                store, job_id="org:alpha", owner_id="new",
                now=NOW, lease_duration=LEASE,
            )
            assert blocked.phase == "blocked"
            reclaimed = reconcile_od5a_boundary_once(
                store, job_id="org:alpha", owner_id="new",
                now=NOW + LEASE + timedelta(seconds=1),
                lease_duration=LEASE,
            )
            assert reclaimed.phase == "claimed"
            with store.transaction() as uow:
                delivery = next(iter(uow.boundary_deliveries()))
                assert delivery.claim_epoch == 2
                assert delivery.claim_owner_id == "new"
    later = NOW + LEASE + timedelta(seconds=1)
    assert _drive(control, "org:alpha", owner="new", at=later)[0] == "acknowledged"
    assert _drive(killed, "org:alpha", owner="new", at=later)[0] == "acknowledged"
    assert _snapshot(killed, jobs) == _snapshot(control, jobs)


def _independent_worker(path, job, at, barrier, reports):
    with SQLitePersistence(path) as store:
        barrier.wait(timeout=30)
        first = reconcile_od5a_boundary_once(
            store, job_id=job, owner_id="worker:" + job,
            now=at, lease_duration=LEASE,
        )
        if first.phase != "published":
            raise AssertionError("lost first organizational publication")
        steps = [first.phase]
        for _ in range(500):
            result = reconcile_od5a_boundary_once(
                store, job_id=job, owner_id="worker:" + job,
                now=at, lease_duration=LEASE,
            )
            steps.append(result.phase)
            if result.phase == "idle":
                reports.put((job, tuple(steps)))
                return
            if result.phase == "blocked":
                raise AssertionError("independent organizations blocked each other")
        raise RuntimeError("boundary worker exceeded causal limit")


def test_two_real_os_processes_reconcile_separate_organization_clocks(tmp_path):
    jobs = {"org:a": "baseline", "org:b": "structural_combined"}
    control, parallel = tmp_path / "control.db", tmp_path / "parallel.db"
    _seed(control, jobs)
    _seed(parallel, jobs)
    clocks = {"org:a": NOW, "org:b": NOW + timedelta(seconds=10)}
    for job in jobs:
        _drive(control, job, at=clocks[job])
    ctx = get_context("spawn")
    ready = ctx.Barrier(len(jobs))
    reports = ctx.Queue()
    workers = [
        ctx.Process(target=_independent_worker,
                    args=(str(parallel), job, clocks[job], ready, reports))
        for job in jobs
    ]
    try:
        for process in workers:
            process.start()
        for process in workers:
            process.join(timeout=45)
            if process.is_alive():
                process.kill()
                process.join()
                pytest.fail("organizational boundary worker hung")
            assert process.exitcode == 0, f"boundary worker failed: {process.exitcode}"
        completed = dict(reports.get(timeout=5) for _ in jobs)
        assert set(completed) == set(jobs)
        assert all("certified" in steps and steps[-1] == "idle"
                   for steps in completed.values())
    finally:
        for process in workers:
            if process.is_alive():
                process.kill()
                process.join()
        reports.close()
        reports.join_thread()
    assert _snapshot(parallel, jobs) == _snapshot(control, jobs)
