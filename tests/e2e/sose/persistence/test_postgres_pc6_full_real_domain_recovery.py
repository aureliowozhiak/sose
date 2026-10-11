"""PC6 end-to-end: real statecharts, real physical ledger, recurring recovery.

This deliberately does not substitute deterministic terminal test state for
Logistics, O2C, Cards Payments or Record-to-Report. All four effects are
performed by TradingCustomerRecoveryRunner and its actual domain handlers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import pytest

from sose.composition import trading_company_customer as customer
from sose.composition.audit import audit_causal_history
from sose.composition.bindings import SettlementBindingService
from sose.composition.recovery import TradingCustomerRecoveryRunner
from sose.composition.scheduler import RecoverySchedule
from sose.core.resource_identity import ResourcePoolContract
from sose.core.resource_reservations import authoritative_effect_reservation_id
from sose.examples.order_to_cash import simulation as o2c
from sose.persistence.postgres import PostgresPersistence
from sose.persistence.ownership import FencedEnginePersistence

DSN = os.environ.get("SOSE_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="SOSE_TEST_POSTGRES_DSN is required")
ORIGIN = o2c.ORIGIN
INTERVAL = timedelta(hours=1)
SLOT = timedelta(minutes=5)
DOMAINS = (
    "composition.deliver_shipment",
    "composition.complete_external_fulfillment",
    "composition.settle_customer_payment",
    "composition.post_customer_journal",
)
CONTRACTS = (
    "warehouse.dispatch_ready.v1",
    "logistics.delivery_completed.v1",
    "o2c.payment_requested.v1",
    "accounting.entry_requested.v1",
)
INSTANCE = "customer-pc6-replay"


def _name(prefix):
    return prefix + "_" + uuid4().hex[:12]


def _policy():
    return ResourcePoolContract(
        resource_type="pickup_courier", pool_id="pc6-real-crossdomain",
        scope="shared", capacity=1,
    )


def _seed_real_workflow(dsn, ns):
    """Stop synchronous demo before real Logistics, leaving a genuine ACK/Command."""
    original = customer._execute_intent

    def only_seed(store, *, effect_id, fixtures, correlation_id):
        command = store.command(effect_id)
        if command is not None and command.name == DOMAINS[0]:
            raise RuntimeError("pc6 staged real Logistics boundary")
        return original(
            store, effect_id=effect_id, fixtures=fixtures,
            correlation_id=correlation_id,
        )

    with PostgresPersistence(dsn, namespace=ns) as store:
        with patch.object(customer, "_execute_intent", side_effect=only_seed):
            with pytest.raises(RuntimeError, match="pc6 staged real Logistics boundary"):
                customer.run_customer_demand_path(persistence=store, instance_key=INSTANCE)
        with store.boundary_transaction() as uow:
            dispatches = [
                (uow.get_boundary_message(d.message_id),
                 uow.get_boundary_consumption(d.delivery_id))
                for d in uow.boundary_deliveries()
                if d.contract_name == "warehouse.dispatch_ready"
            ]
        assert len(dispatches) == 1
        dispatch, receipt = dispatches[0]
        assert dispatch is not None and receipt is not None
        effect = store.command(receipt.consumer_effect_id)
        assert effect is not None and effect.name == DOMAINS[0]
        assert store.entity("shipment", effect.entity_id).state == "created"
        return effect.correlation_id, effect.command_id


def _schedule(domain, shared, *, organization, correlation, max_actions=1):
    runner = TradingCustomerRecoveryRunner(
        persistence=domain, owner_id=f"pc6-{organization}",
        job_id=f"real-pc6-{organization}", max_actions=max_actions,
        resource_persistence=shared,
        resource_policies={DOMAINS[0]: _policy()},
        resource_organizations={correlation: organization},
        resource_slot_duration=SLOT, resource_retry_delay=SLOT,
    )
    return RecoverySchedule(
        runner, start_at=ORIGIN, interval=INTERVAL, max_slots=1,
    )


def _tick(dsn, ns, shared_ns, org, correlation, target_tick):
    """Fresh connections and a persistent schedule, not a direct domain E2E call."""
    with PostgresPersistence(dsn, namespace=ns) as domain:
        with PostgresPersistence(dsn, namespace=shared_ns) as shared:
            state = domain.job_state(f"real-pc6-{org}")
            next_tick = state.next_tick if state is not None else 0
            assert next_tick == target_tick, (org, next_tick, target_tick)
            result = _schedule(
                domain, shared, organization=org, correlation=correlation,
            ).run_due(now=ORIGIN + target_tick * INTERVAL)
            assert len(result) == 1
            assert domain.job_state(f"real-pc6-{org}").next_tick == target_tick + 1
            return result[0].actions


def _terminal(dsn, ns):
    with PostgresPersistence(dsn, namespace=ns) as store:
        return {c.entity_type for c in store.business_effects()} >= {
            "shipment", "sales_order", "card_payment", "journal_entry",
        }


def _advance(dsn, ns, shared_ns, org, corr, *, max_ticks=18):
    for n in range(max_ticks):
        if _terminal(dsn, ns):
            return n
        _tick(dsn, ns, shared_ns, org, corr, n)
    assert _terminal(dsn, ns), f"full real domain chain did not converge: {org}"
    return max_ticks


def _canonical_objects(items):
    return tuple(sorted(
        json.dumps(asdict(x), default=str, sort_keys=True, separators=(",", ":"))
        for x in items
    ))


def _proof(dsn, domains, physical_ns, seeds):
    with PostgresPersistence(dsn, namespace=physical_ns) as shared:
        assert shared.temporal_resources().audit()
        ledger = shared.temporal_resources().snapshot()
        serialized = json.dumps(ledger, sort_keys=True, default=str)
        for org, ns in sorted(domains.items()):
            physical_id = authoritative_effect_reservation_id(
                seeds[org][1], scope=ns,
            )
            assert physical_id in serialized
            serialized = serialized.replace(
                physical_id, f"physical:{org}:{seeds[org][1]}",
            )
        ledger = json.loads(serialized)
        for name in ("reservations", "outages", "events"):
            ledger[name].sort()
    evidence = {}
    for org, ns in sorted(domains.items()):
        with PostgresPersistence(dsn, namespace=ns) as store:
            audit_lease = store.claim_writer(
                f"pc6-audit-{org}", expected_epoch=store.writer_epoch(),
            )
            view = FencedEnginePersistence(store, audit_lease)
            certs = view.business_effects()
            assert len(certs) == 4, (org, certs)
            assert {c.entity_type for c in certs} == {
                "shipment", "sales_order", "card_payment", "journal_entry",
            }
            assert all(store.command(c.effect_id) is None for c in certs)
            audit = audit_causal_history(view)
            with view.boundary_transaction() as uow:
                deliveries = tuple(uow.boundary_deliveries())
                relevant = tuple(sorted(
                    (d.message_id, d.status.value, d.consumer_effect_id,
                     uow.get_boundary_consumption(d.delivery_id).consumption_id)
                    for d in deliveries if d.status.value == "consumed"
                ))
                messages = tuple(
                    uow.get_boundary_message(d.message_id) for d in deliveries
                )
            by_message_id = {m.message_id: m for m in messages if m is not None}
            assert len(by_message_id) == len(messages), "duplicate boundary message identity"
            causal_edges = tuple(sorted(
                (m.causation_id, m.message_id)
                for m in messages if m is not None
                and m.causation_id in by_message_id
            ))
            assert len(causal_edges) == len(messages) - 1, (
                "real Trading Company boundary lineage is incomplete", causal_edges,
            )
            for parent_id, child_id in causal_edges:
                parent, child = by_message_id[parent_id], by_message_id[child_id]
                assert parent.correlation_id == child.correlation_id
                assert parent.produced_at <= child.produced_at
            binding = SettlementBindingService(view).for_order(
                next(c.entity_id for c in certs if c.entity_type == "sales_order")
            )
            assert binding is not None
            state = store.job_state(f"real-pc6-{org}")
            assert state is not None and state.active_trigger_id is None
            evidence[org] = {
                "semantic_digest": audit.semantic_digest,
                "typed_edges": audit.typed_edges,
                "boundary_causal_edges": causal_edges,
                "messages": _canonical_objects(messages),
                "ack_receipts": relevant,
                "entities": _canonical_objects(store.entities()),
                "events": _canonical_objects(store.events()),
                "certificates": _canonical_objects(certs),
                "binding": asdict(binding),
                "scheduled": _canonical_objects(store.scheduled_work()),
                "resources": _canonical_objects(store.resource_reservations()),
                "stores": _canonical_objects(store.store_items()),
                "containers": _canonical_objects(store.container_states()),
                "sinks": _canonical_objects(store.sink_checkpoints()),
                "position": store.simulation_position(),
                "job_state": state,
            }
    return {"organizations": evidence, "physical": ledger}


def _run(dsn, *, killed=False, cut="after_logistics_effect"):
    domains = {"a": _name("pc6fulla"), "b": _name("pc6fullb")}
    shared_ns = _name("pc6fullphysical")
    seeds = {org: _seed_real_workflow(dsn, ns) for org, ns in domains.items()}
    assert seeds["a"][1] == seeds["b"][1]
    assert seeds["a"][0] == seeds["b"][0]

    if killed:
        child = subprocess.run(
            [sys.executable, "-c", _KILL_PROCESS, dsn, domains["a"], shared_ns,
             seeds["a"][0], cut],
            text=True, capture_output=True, check=False, timeout=90,
        )
        assert child.returncode == 79, (cut, child.stderr[-2500:])
        with PostgresPersistence(dsn, namespace=domains["a"]) as dead:
            state = dead.job_state("real-pc6-a")
            assert state is not None and state.active_trigger_id is not None
        # Organization B advances separately even though A has a still-active
        # durable occurrence and owns its own independent operational writer.
        _tick(dsn, domains["b"], shared_ns, "b", seeds["b"][0], 0)
        with PostgresPersistence(dsn, namespace=domains["a"]) as recovered:
            with PostgresPersistence(dsn, namespace=shared_ns) as physical:
                restarted = _schedule(
                    recovered, physical, organization="a", correlation=seeds["a"][0],
                ).run_due(now=ORIGIN)
                assert len(restarted) == 1
                assert recovered.job_state("real-pc6-a").next_tick == 1
    else:
        _tick(dsn, domains["a"], shared_ns, "a", seeds["a"][0], 0)
        _tick(dsn, domains["b"], shared_ns, "b", seeds["b"][0], 0)

    # A and B advance without a common clock, but each retains its own slots.
    for org in ("a", "b"):
        ns = domains[org]
        for n in range(1, 22):
            if _terminal(dsn, ns):
                break
            _tick(dsn, ns, shared_ns, org, seeds[org][0], n)
        assert _terminal(dsn, ns), org
    return _proof(dsn, domains, shared_ns, seeds)


_KILL_PROCESS = """
import os, sys
from datetime import timedelta
from sose.composition.effects import BusinessEffectService
from sose.composition.recovery import TradingCustomerRecoveryRunner
from sose.composition.scheduler import RecoverySchedule
from sose.core.resource_identity import ResourcePoolContract
from sose.examples.order_to_cash import simulation as o2c
from sose.persistence.postgres import PostgresPersistence
dsn, domain_ns, physical_ns, corr, cut, *tail = sys.argv[1:]
slot = int(tail[0]) if tail else 0
old = TradingCustomerRecoveryRunner._execute_pending
def killed(store, source, effect_id, *, authoritative_pickup=None, resource_persistence=None):
    old(store, source, effect_id,
        authoritative_pickup=authoritative_pickup,
        resource_persistence=resource_persistence)
    selected = {
        "after_logistics_effect": "warehouse.dispatch_ready.v1",
        "after_o2c_effect": "logistics.delivery_completed.v1",
        "after_payments_effect": "o2c.payment_requested.v1",
        "after_r2r_effect": "accounting.entry_requested.v1",
    }
    if source.contract_key == selected.get(cut):
        assert store.command(effect_id) is None
        assert any(c.effect_id == effect_id for c in store.business_effects())
        os._exit(79)
TradingCustomerRecoveryRunner._execute_pending = staticmethod(killed)
original_complete = BusinessEffectService.complete
terminal_by_name = {
    "composition.deliver_shipment": "delivered",
    "composition.complete_external_fulfillment": "invoiced",
    "composition.settle_customer_payment": "settled",
    "composition.post_customer_journal": "posted",
}
cut_for_name = {
    "before_logistics_certificate": "composition.deliver_shipment",
    "before_o2c_certificate": "composition.complete_external_fulfillment",
    "before_payments_certificate": "composition.settle_customer_payment",
    "before_r2r_certificate": "composition.post_customer_journal",
}
def death_before_certificate(self, *, effect_id, completed_at):
    command = self.persistence.command(effect_id)
    if command is not None and command.name == cut_for_name.get(cut):
        terminal = self.persistence.entity(command.entity_type, command.entity_id)
        assert terminal is not None and terminal.state == terminal_by_name[command.name]
        assert not any(c.effect_id == effect_id for c in self.persistence.business_effects())
        os._exit(79)
    return original_complete(self, effect_id=effect_id, completed_at=completed_at)
BusinessEffectService.complete = death_before_certificate
with PostgresPersistence(dsn, namespace=domain_ns) as domain:
    with PostgresPersistence(dsn, namespace=physical_ns) as physical:
        runner = TradingCustomerRecoveryRunner(
            persistence=domain, owner_id="killed-real-a", job_id="real-pc6-a",
            max_actions=1, resource_persistence=physical,
            resource_policies={"composition.deliver_shipment": ResourcePoolContract(
                resource_type="pickup_courier", pool_id="pc6-real-crossdomain",
                scope="shared", capacity=1,
            )},
            resource_organizations={corr: "a"},
            resource_slot_duration=timedelta(minutes=5),
            resource_retry_delay=timedelta(minutes=5),
        )
        RecoverySchedule(
            runner, start_at=o2c.ORIGIN, interval=timedelta(hours=1), max_slots=1,
        ).run_due(now=o2c.ORIGIN + slot * timedelta(hours=1))
raise AssertionError("OS-kill probe did not reach target")
"""


def _record_equivalence(name, baseline, recovered, *, default_path=None):
    """Append an auditable independently verified cut; do not only certify one."""
    target = os.environ.get("SOSE_PC6_REAL_MULTIDOMAIN_REPORT")
    if target is None and default_path is None:
        return
    destination = Path(target if target is not None else default_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = (
        json.loads(destination.read_text(encoding="utf-8"))
        if destination.exists() else {
            "protocol": "pc6-real-multidomain-recurring-v2",
            "organizations": ["a", "b"],
            "real_domain_handlers": list(DOMAINS),
            "physical_pool": "pickup_courier/shared/pc6-real-crossdomain/capacity-1",
            "termination": "os._exit(79) in separate worker process",
            "cases": [],
        }
    )
    reference = json.dumps(baseline, sort_keys=True, default=str)
    replay = json.dumps(recovered, sort_keys=True, default=str)
    case = {
        "fault": name,
        "equivalent": baseline == recovered,
        "reference_sha256": sha256(reference.encode()).hexdigest(),
        "recovered_sha256": sha256(replay.encode()).hexdigest(),
        "certificates_per_organization": {
            org: len(baseline["organizations"][org]["certificates"])
            for org in ("a", "b")
        },
    }
    if any(entry["fault"] == name for entry in report["cases"]):
        raise AssertionError(f"duplicated certified fault case: {name}")
    report["cases"].append(case)
    report["cases"].sort(key=lambda item: item["fault"])
    report["all_equivalent"] = all(entry["equivalent"] for entry in report["cases"])
    destination.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )


def test_pg_two_full_real_domain_chains_replay_worker_death_with_shared_physical_pool(
    tmp_path,
):
    assert DSN is not None
    baseline = _run(DSN)
    recovered = _run(DSN, killed=True)
    assert recovered == baseline
    _record_equivalence(
        "after_logistics_certificate", baseline, recovered,
        default_path=tmp_path / "pc6-real-multidomain.json",
    )


def _pending_domain_effect(dsn, ns, intent_name):
    from sose.composition.model import DeliveryStatus

    with PostgresPersistence(dsn, namespace=ns) as store:
        with store.transaction(owner_epoch=store.writer_epoch()) as uow:
            for delivery in uow.boundary_deliveries():
                if delivery.status is not DeliveryStatus.CONSUMED:
                    continue
                receipt = uow.get_boundary_consumption(delivery.delivery_id)
                if receipt is None:
                    raise RuntimeError("consumed delivery lost its durable receipt")
                command = uow.get_command(receipt.consumer_effect_id)
                if command is not None and command.name == intent_name:
                    return True
    return False


def _run_real_domain_cut(dsn, *, name, killed, before_certificate=False):
    domains = {"a": _name("pc6cut_a"), "b": _name("pc6cut_b")}
    shared_ns = _name("pc6cut_physical")
    seeds = {org: _seed_real_workflow(dsn, ns) for org, ns in domains.items()}
    slot = 0
    while not _pending_domain_effect(dsn, domains["a"], name):
        assert slot < 18, f"target domain never acquired a durable Command: {name}"
        _tick(dsn, domains["a"], shared_ns, "a", seeds["a"][0], slot)
        slot += 1
    assert not _terminal(dsn, domains["a"])
    if killed:
        cut = (
            {
                DOMAINS[0]: "before_logistics_certificate",
                DOMAINS[1]: "before_o2c_certificate",
                DOMAINS[2]: "before_payments_certificate",
                DOMAINS[3]: "before_r2r_certificate",
            } if before_certificate else {
                DOMAINS[0]: "after_logistics_effect",
                DOMAINS[1]: "after_o2c_effect",
                DOMAINS[2]: "after_payments_effect",
                DOMAINS[3]: "after_r2r_effect",
            }
        )[name]
        child = subprocess.run(
            [sys.executable, "-c", _KILL_PROCESS, dsn, domains["a"],
             shared_ns, seeds["a"][0], cut, str(slot)],
            capture_output=True, text=True, check=False, timeout=90,
        )
        assert child.returncode == 79, (name, child.stderr[-1800:])
        with PostgresPersistence(dsn, namespace=domains["a"]) as dead:
            assert dead.job_state("real-pc6-a").active_trigger_id is not None
            entity_type = {
                DOMAINS[0]: "shipment", DOMAINS[1]: "sales_order",
                DOMAINS[2]: "card_payment", DOMAINS[3]: "journal_entry",
            }[name]
            certified = any(
                c.entity_type == entity_type for c in dead.business_effects()
            )
            assert certified is not before_certificate
            if before_certificate:
                assert _pending_domain_effect(dsn, domains["a"], name)
    else:
        _tick(dsn, domains["a"], shared_ns, "a", seeds["a"][0], slot)

    # Deliberately progress B while A's initial occurrence remains unfinished.
    _tick(dsn, domains["b"], shared_ns, "b", seeds["b"][0], 0)
    if killed:
        with PostgresPersistence(dsn, namespace=domains["a"]) as a:
            with PostgresPersistence(dsn, namespace=shared_ns) as physical:
                replayed = _schedule(
                    a, physical, organization="a", correlation=seeds["a"][0],
                ).run_due(now=ORIGIN + slot * INTERVAL)
                assert len(replayed) == 1
                assert a.job_state("real-pc6-a").next_tick == slot + 1

    for org, first_slot in (("a", slot + 1), ("b", 1)):
        for n in range(first_slot, 25):
            if _terminal(dsn, domains[org]):
                break
            _tick(dsn, domains[org], shared_ns, org, seeds[org][0], n)
        assert _terminal(dsn, domains[org])
    return _proof(dsn, domains, shared_ns, seeds)


@pytest.mark.parametrize("intent_name", DOMAINS[1:])
def test_pg_real_nonphysical_domain_certification_after_os_kill_preserves_slot(intent_name):
    """No certified business effect may advance its original slot after death."""
    assert DSN is not None
    baseline = _run_real_domain_cut(DSN, name=intent_name, killed=False)
    recovered = _run_real_domain_cut(DSN, name=intent_name, killed=True)
    assert recovered == baseline
    _record_equivalence(f"after_{intent_name}_certificate", baseline, recovered)


@pytest.mark.parametrize("intent_name", DOMAINS)
def test_pg_real_statechart_commits_but_worker_dies_before_business_certificate(intent_name):
    """Actual durable domain event survives death without an invented certificate."""
    assert DSN is not None
    baseline = _run_real_domain_cut(DSN, name=intent_name, killed=False)
    resumed = _run_real_domain_cut(
        DSN, name=intent_name, killed=True, before_certificate=True,
    )
    assert resumed == baseline
    _record_equivalence(f"before_{intent_name}_certificate", baseline, resumed)


def _seed_before_logistics_ack(dsn, ns):
    """Real customer path stops before the Logistics claim, not at fake state."""
    from sose.composition.model import DeliveryStatus

    original = customer._consume_next

    def stop_at_dispatch(service, registry, *, owner_id, now, expected_message_id):
        with service.persistence.boundary_transaction() as uow:
            message = uow.get_boundary_message(expected_message_id)
        if message is not None and message.contract_key == CONTRACTS[0]:
            raise RuntimeError("pc6 stage before real Logistics claim")
        return original(
            service, registry, owner_id=owner_id, now=now,
            expected_message_id=expected_message_id,
        )

    with PostgresPersistence(dsn, namespace=ns) as store:
        with patch.object(customer, "_consume_next", side_effect=stop_at_dispatch):
            with pytest.raises(RuntimeError, match="before real Logistics claim"):
                customer.run_customer_demand_path(
                    persistence=store, instance_key=INSTANCE,
                )
        with store.boundary_transaction() as uow:
            dispatches = [
                (uow.get_boundary_message(delivery.message_id), delivery)
                for delivery in uow.boundary_deliveries()
                if delivery.contract_name == "warehouse.dispatch_ready"
            ]
        assert len(dispatches) == 1
        message, delivery = dispatches[0]
        assert message is not None
        assert delivery.status is DeliveryStatus.PENDING
        assert store.entity("shipment", message.payload()["shipment_id"]).state == "created"
        effect_id = customer.deterministic_id(
            "composition-domain-intent", message.message_id, DOMAINS[0],
            "shipment", str(message.payload()["shipment_id"]),
        )
        assert store.command(effect_id) is None
        return message.correlation_id, effect_id, delivery.delivery_id


_KILL_REAL_BOUNDARY_PROCESS = """
import os, sys
from datetime import timedelta
from sose.composition.boundary import BoundaryService
from sose.composition.recovery import TradingCustomerRecoveryRunner
from sose.composition.scheduler import RecoverySchedule
from sose.core.resource_identity import ResourcePoolContract
from sose.examples.order_to_cash import simulation as o2c
from sose.persistence.postgres import PostgresPersistence

dsn, domain_ns, physical_ns, correlation, cut = sys.argv[1:]
original_claim = BoundaryService.claim_next
original_consume = BoundaryService.consume
def claimed(self, **kwargs):
    if cut == "after_claim" and kwargs.get("destination_domain") == "logistics":
        # Expire the dead worker's *physical* lease before its logical replay.
        # The later recovered ACK still uses the reference slot's logical time.
        kwargs = dict(kwargs)
        kwargs["now"] = kwargs["now"] - timedelta(hours=2)
        kwargs["lease_duration"] = timedelta(seconds=1)
    lease = original_claim(self, **kwargs)
    if cut == "after_claim" and lease is not None and kwargs.get("destination_domain") == "logistics":
        os._exit(79)
    return lease
def consumed(self, *, lease, registry, now):
    receipt = original_consume(self, lease=lease, registry=registry, now=now)
    if cut == "after_ack" and receipt is not None:
        assert self.persistence.command(receipt.consumer_effect_id) is not None
        os._exit(79)
    return receipt
BoundaryService.claim_next = claimed
BoundaryService.consume = consumed
with PostgresPersistence(dsn, namespace=domain_ns) as domain:
    with PostgresPersistence(dsn, namespace=physical_ns) as physical:
        runner = TradingCustomerRecoveryRunner(
            persistence=domain, owner_id="fatal-real-boundary-a",
            job_id="real-pc6-a", max_actions=1,
            resource_persistence=physical,
            resource_policies={
                "composition.deliver_shipment": ResourcePoolContract(
                    resource_type="pickup_courier", pool_id="pc6-real-crossdomain",
                    scope="shared", capacity=1,
                ),
            },
            resource_organizations={correlation: "a"},
            resource_slot_duration=timedelta(minutes=5),
            resource_retry_delay=timedelta(minutes=5),
        )
        RecoverySchedule(
            runner, start_at=o2c.ORIGIN, interval=timedelta(hours=1),
            max_slots=1,
        ).run_due(now=o2c.ORIGIN)
raise AssertionError("real boundary OS-kill probe did not fire")
"""


def _run_real_boundary_cut(dsn, *, cut=None):
    from sose.composition.boundary import BoundaryService
    from sose.composition.model import DeliveryStatus

    domains = {"a": _name("pc6ack_a"), "b": _name("pc6ack_b")}
    physical_ns = _name("pc6ack_shared")
    seeded = {org: _seed_before_logistics_ack(dsn, ns) for org, ns in domains.items()}
    seeds = {org: values[:2] for org, values in seeded.items()}
    assert seeds["a"] == seeds["b"]
    if cut is None:
        _tick(dsn, domains["a"], physical_ns, "a", seeds["a"][0], 0)
    else:
        child = subprocess.run(
            [sys.executable, "-c", _KILL_REAL_BOUNDARY_PROCESS,
             dsn, domains["a"], physical_ns, seeds["a"][0], cut],
            text=True, capture_output=True, check=False, timeout=90,
        )
        assert child.returncode == 79, (cut, child.stderr[-2400:])
        with PostgresPersistence(dsn, namespace=domains["a"]) as dead:
            state = dead.job_state("real-pc6-a")
            assert state is not None and state.active_trigger_id is not None
            delivery = BoundaryService(dead).delivery(seeded["a"][2])
            assert delivery is not None
            assert delivery.status is (
                DeliveryStatus.CLAIMED if cut == "after_claim"
                else DeliveryStatus.CONSUMED
            )
            if cut == "after_ack":
                assert dead.command(seeds["a"][1]) is not None
                assert BoundaryService(dead).consumption(delivery.delivery_id) is not None
            else:
                assert BoundaryService(dead).consumption(delivery.delivery_id) is None

    # Prove B can advance while A's original trigger remains unfinished.
    _tick(dsn, domains["b"], physical_ns, "b", seeds["b"][0], 0)
    if cut is not None:
        with PostgresPersistence(dsn, namespace=domains["a"]) as recovered:
            with PostgresPersistence(dsn, namespace=physical_ns) as physical:
                replay = _schedule(
                    recovered, physical, organization="a", correlation=seeds["a"][0],
                ).run_due(now=ORIGIN)
                assert len(replay) == 1
                assert recovered.job_state("real-pc6-a").next_tick == 1

    for org in ("a", "b"):
        for tick in range(1, 26):
            if _terminal(dsn, domains[org]):
                break
            _tick(dsn, domains[org], physical_ns, org, seeds[org][0], tick)
        assert _terminal(dsn, domains[org]), (cut, org)
    return _proof(dsn, domains, physical_ns, seeds)


@pytest.mark.parametrize("cut", ("after_claim", "after_ack"))
def test_pg_real_logistics_boundary_worker_death_preserves_recurring_slot(cut):
    """Real ACK/Command and four subsequent real statecharts; no reference terminal states."""
    assert DSN is not None
    baseline = _run_real_boundary_cut(DSN)
    recovered = _run_real_boundary_cut(DSN, cut=cut)
    assert recovered == baseline, f"recurring slot advanced incorrectly after {cut}"
    _record_equivalence(f"real_logistics_{cut}", baseline, recovered)
