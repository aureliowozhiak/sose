"""PC6-specific transport and database failure around atomic boundary ACK+Command.

Unlike canonical engine chaos, this exercises a genuine Trading Company
Logistics BoundaryService.consume() transaction and subsequent real handlers.
No post-failure application success is inferred from a client exception.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from sose.composition.model import DeliveryStatus
from sose.persistence.postgres import PostgresPersistence
from tests.e2e.sose.persistence.test_postgres_pc6_full_real_domain_recovery import (
    _seed_before_logistics_ack, _proof, _terminal, _tick,
)
from tests.e2e.sose.persistence.test_postgres_infrastructure_chaos import (
    _docker, _free_port, _start_proxy, _wait_postgres,
)
from tests.support.chaos_waits import wait_for_marker_exists, wait_for_process_exit

DSN = os.environ.get("SOSE_TEST_POSTGRES_DSN")
CONTAINER_ID = os.environ.get("SOSE_POSTGRES_CONTAINER_ID")
pytestmark = pytest.mark.skipif(not DSN, reason="PostgreSQL required")

_ACK_WORKER = """
import os, sys, time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from sose.composition.boundary import BoundaryService
from sose.composition.recovery import TradingCustomerRecoveryRunner
from sose.persistence.postgres import PostgresPersistence

dsn, namespace, phase, marker, continue_file = sys.argv[1:]
with PostgresPersistence(dsn, namespace=namespace) as store:
    service = BoundaryService(store)
    lease = service.claim_next(
        owner_id="ambiguous-ack-worker", now=__import__("sose.examples.order_to_cash.simulation", fromlist=["ORIGIN"]).ORIGIN,
        lease_duration=timedelta(seconds=1),
        destination_domain="logistics",
        accepted_contracts=frozenset({("warehouse.dispatch_ready", 1)}),
    )
    assert lease is not None
    with store.boundary_transaction() as uow:
        message = uow.get_boundary_message(lease.message_id)
    assert message is not None
    original = store.boundary_transaction
    @contextmanager
    def faulting_transaction(*, owner_epoch=None):
        with original(owner_epoch=owner_epoch) as uow:
            yield uow
            if phase == "before_commit":
                Path(marker).write_text("before_commit")
                wait(continue_file)
        if phase == "after_commit":
            Path(marker).write_text("after_commit")
            wait(continue_file)
    def wait(name):
        deadline = time.monotonic() + 25
        while not Path(name).exists():
            if time.monotonic() > deadline:
                raise TimeoutError("parent never delivered fault")
            time.sleep(.025)
    store.boundary_transaction = faulting_transaction
    receipt = service.consume(
        lease=lease, registry=TradingCustomerRecoveryRunner._registry_for(message),
        now=__import__("sose.examples.order_to_cash.simulation", fromlist=["ORIGIN"]).ORIGIN,
    )
    # A transport break may make the caller's apparent outcome uncertain.
    assert receipt is not None
    store.writer_epoch()
"""


def _boundary_receipt(dsn, ns, delivery_id):
    with PostgresPersistence(dsn, namespace=ns) as store:
        with store.boundary_transaction() as uow:
            delivery = uow.get_boundary_delivery(delivery_id)
            receipt = uow.get_boundary_consumption(delivery_id)
            assert delivery is not None
            if delivery.status is DeliveryStatus.CONSUMED:
                assert receipt is not None
                assert uow.get_command(receipt.consumer_effect_id) is not None
            else:
                assert receipt is None
            return delivery.status, receipt is not None


def _complete(dsn, domains, physical, seeds):
    for org in ("a", "b"):
        for tick in range(26):
            if _terminal(dsn, domains[org]):
                break
            _tick(dsn, domains[org], physical, org, seeds[org][0], tick)
        assert _terminal(dsn, domains[org])
    return _proof(dsn, domains, physical, seeds)


def _scenario(tmp_path, *, phase, transport):
    domains = {org: f"commit_{org}_{uuid4().hex[:12]}" for org in ("a", "b")}
    physical = f"commit_phys_{uuid4().hex[:12]}"
    seeded = {org: _seed_before_logistics_ack(DSN, ns)
              for org, ns in domains.items()}
    seeds = {org: data[:2] for org, data in seeded.items()}
    marker = tmp_path / f"{phase}-{transport}-paused"
    continuation = tmp_path / f"{phase}-{transport}-go"
    marker.unlink(missing_ok=True)
    continuation.unlink(missing_ok=True)
    proxy = None
    worker = None
    try:
        if transport == "proxy":
            port = _free_port()
            proxy, worker_dsn = _start_proxy(
                DSN, port=port, marker=tmp_path / "proxy-ready",
            )
        else:
            worker_dsn = DSN
        worker = subprocess.Popen(
            [sys.executable, "-c", _ACK_WORKER, worker_dsn, domains["a"],
             phase, str(marker), str(continuation)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        wait_for_marker_exists(
            marker, worker, timeout=35,
            premature_exit_label="ACK worker exited before COMMIT cut",
            timeout_label="ACK worker failed to reach COMMIT cut",
            termination_timeout=10,
        )
        if transport == "proxy":
            assert proxy is not None
            proxy.kill()
            wait_for_process_exit(
                proxy, timeout=10, label="killed transport", termination_timeout=10,
            )
        else:
            assert CONTAINER_ID
            _docker("stop", "-t", "1", CONTAINER_ID)
        continuation.write_text("go", encoding="utf-8")
        try:
            worker.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.communicate(timeout=10)
        assert worker.returncode != 0
    finally:
        if transport == "server" and CONTAINER_ID:
            _docker("start", CONTAINER_ID)
            _wait_postgres(DSN)
        if worker is not None and worker.poll() is None:
            worker.kill()
            worker.communicate(timeout=10)
        if proxy is not None and proxy.poll() is None:
            proxy.kill()
            proxy.communicate(timeout=10)

    # NEVER infer commit outcome from the failing client. A separate connection
    # must resolve the durable ACK+Command fact before any replay.
    status, committed = _boundary_receipt(DSN, domains["a"], seeded["a"][2])
    if phase == "before_commit":
        assert not committed
    else:
        assert committed
    assert status is (DeliveryStatus.CONSUMED if committed else DeliveryStatus.CLAIMED)

    # During A's outage, B retains an autonomous namespace and original clock.
    _tick(DSN, domains["b"], physical, "b", seeds["b"][0], 0)
    for tick in range(26):
        if _terminal(DSN, domains["a"]):
            break
        _tick(DSN, domains["a"], physical, "a", seeds["a"][0], tick,
              observed_delay=timedelta(seconds=2))
    assert _terminal(DSN, domains["a"])
    for tick in range(1, 26):
        if _terminal(DSN, domains["b"]):
            break
        _tick(DSN, domains["b"], physical, "b", seeds["b"][0], tick)
    assert _terminal(DSN, domains["b"])
    return _proof(DSN, domains, physical, seeds)


@pytest.mark.parametrize("phase", ("before_commit", "after_commit"))
def test_real_pc6_atomic_ack_survives_transport_ambiguity(tmp_path, phase):
    assert DSN
    snapshot = _scenario(tmp_path, phase=phase, transport="proxy")
    assert all(len(snapshot["organizations"][org]["certificates"]) == 4
               for org in ("a", "b"))


@pytest.mark.parametrize("phase", ("before_commit", "after_commit"))
def test_real_pc6_atomic_ack_survives_postgres_restart(tmp_path, phase):
    if not CONTAINER_ID:
        pytest.skip("real PostgreSQL container control is mandatory for server restart")
    snapshot = _scenario(tmp_path, phase=phase, transport="server")
    assert all(len(snapshot["organizations"][org]["certificates"]) == 4
               for org in ("a", "b"))
