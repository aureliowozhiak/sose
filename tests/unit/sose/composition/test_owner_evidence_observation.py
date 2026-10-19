"""#496 bounded read-side falsifiers: no global org truth or actor instantiation."""
from datetime import datetime, timezone
from dataclasses import replace

import pytest

from sose.composition.boundary import BoundaryConsumerRegistry
from sose.composition.observation import observe_organization_events
from sose.composition.organization import (
    OrganizationDefinition, ProcessComponent, ScheduledJob, PhysicalPoolRef,
)
from sose.core.events import DomainEvent
from sose.examples.catalog import builtin_catalog
from sose.examples.process_manifest import builtin_process_manifests
from sose.persistence.memory import MemoryPersistence
from sose.persistence.sqlite import SQLitePersistence


NOW = datetime(2026, 10, 18, 15, tzinfo=timezone.utc)


def definition(*, owner_a="org:a", owner_b="org:b"):
    return OrganizationDefinition(
        organization_id="organization:observation-only",
        version=1,
        components=(
            ProcessComponent(
                "fulfillment", "warehouse_fulfillment", owner_a,
                ("FulfillmentOrderChart",),
            ),
            ProcessComponent(
                "warehouse", "warehouse_management", owner_b,
                ("WarehouseSiteChart",),
            ),
        ),
        jobs=(
            ScheduledJob("job:fulfillment", "fulfillment", "trigger:fulfillment"),
            ScheduledJob("job:warehouse", "warehouse", "trigger:warehouse"),
        ),
    )


def registered_type(catalog, domain, chart):
    return next(
        entry.name for entry in catalog.get(domain).registered_entity_types
        if entry.chart_factory.__name__ == chart
    )


def observe(spec, store, *, catalog=None):
    return observe_organization_events(
        spec, store,
        catalog=catalog or builtin_catalog(),
        manifests=builtin_process_manifests(),
        consumers=BoundaryConsumerRegistry(),
    )


def append(store, *, owner, kind, event_id,
           name="entity.state_transition", payload=None):
    if payload is None:
        payload = {
            "trigger": "assign", "from_state": "eligible",
            "to_state": "active",
        }
    with store.transaction(owner_id=owner) as uow:
        uow.append_event(DomainEvent(
            event_id=event_id, name=name,
            entity_type=kind, entity_id="entity:" + event_id,
            occurred_at=NOW, owner_id=owner,
            payload=payload,
        ))


@pytest.mark.parametrize("adapter", ("memory", "sqlite"))
def test_two_component_evidence_is_owner_scoped_ordered_and_recoverable(adapter, tmp_path):
    path = tmp_path / "organization-read.sqlite"
    store = MemoryPersistence() if adapter == "memory" else SQLitePersistence(path)
    catalog = builtin_catalog()
    spec = definition()
    wf = registered_type(catalog, "warehouse_fulfillment", "FulfillmentOrderChart")
    wm = registered_type(catalog, "warehouse_management", "WarehouseSiteChart")
    try:
        append(store, owner="org:b", kind=wm, event_id="b:1")
        append(store, owner="org:outside", kind=wf, event_id="outside")
        append(store, owner="org:a", kind=wf, event_id="a:1")
        append(store, owner="org:b", kind=wm, event_id="b:2")
        append(store, owner="org:a", kind=wf, event_id="a:2")
        append(store, owner="org:a", kind="some.unadmitted.event", event_id="a:unverified")
        before = tuple(store.events())
        first = observe(spec, store, catalog=catalog)
        second = observe(spec, store, catalog=catalog)
        assert first == second
        assert tuple(store.events()) == before
        assert first.organization_id == spec.organization_id
        assert first.definition_fingerprint == spec.fingerprint()
        a, b = first.components
        assert (a.component_id, a.owner_id, a.event_ids) == (
            "fulfillment", "org:a", ("a:1", "a:2")
        )
        assert (b.component_id, b.owner_id, b.event_ids) == (
            "warehouse", "org:b", ("b:1", "b:2")
        )
        assert a.declared_job_ids == ("job:fulfillment",)
        assert b.declared_job_ids == ("job:warehouse",)
        assert "outside" not in a.event_ids + b.event_ids
        assert "a:unverified" not in a.event_ids + b.event_ids
    finally:
        if adapter == "sqlite":
            store.close()
    if adapter == "sqlite":
        with SQLitePersistence(path) as recovered:
            assert observe(spec, recovered, catalog=catalog) == first


@pytest.mark.parametrize("adapter", ("memory", "sqlite"))
def test_observation_rejects_wrong_owner_of_other_admitted_statechart(adapter, tmp_path):
    path = tmp_path / "wrong-owner.sqlite"
    store = MemoryPersistence() if adapter == "memory" else SQLitePersistence(path)
    catalog = builtin_catalog()
    wm = registered_type(catalog, "warehouse_management", "WarehouseSiteChart")
    try:
        append(store, owner="org:a", kind=wm, event_id="forged-cross-owner")
        before = tuple(store.events())
        with pytest.raises(ValueError, match="owner/event StateChart type"):
            observe(definition(), store, catalog=catalog)
        assert tuple(store.events()) == before
    finally:
        if adapter == "sqlite":
            store.close()


def test_observation_fails_closed_for_ambiguous_reused_owner_across_domains():
    with pytest.raises(ValueError, match="distinct component owner_id"):
        observe(definition(owner_a="org:shared", owner_b="org:shared"),
                MemoryPersistence())


def test_observation_refuses_self_attested_pool_before_any_persistence_read():
    spec = definition()
    pool = PhysicalPoolRef("pool:fiction", "pool:owner",
                           ("fulfillment", "warehouse"))
    invalid = replace(spec, physical_pools=(pool,))
    class NeverRead:
        def events(self):
            raise AssertionError("unadmitted config was allowed to read runtime")

    with pytest.raises(ValueError, match="authoritative resource"):
        observe(invalid, NeverRead())


@pytest.mark.parametrize("adapter", ("memory", "sqlite"))
def test_entity_type_alone_cannot_invent_statechart_transition_evidence(adapter, tmp_path):
    """Same owner/type with unrelated DomainEvent name is not StateChart evidence."""
    path = tmp_path / "non-statechart.sqlite"
    store = MemoryPersistence() if adapter == "memory" else SQLitePersistence(path)
    catalog = builtin_catalog()
    kind = registered_type(catalog, "warehouse_fulfillment", "FulfillmentOrderChart")
    try:
        append(store, owner="org:a", kind=kind, event_id="not-a-transition",
               name="component.config_change", payload={"source": "unaudited"})
        append(store, owner="org:a", kind=kind, event_id="verified-transition")
        before = tuple(store.events())
        projected = observe(definition(), store, catalog=catalog)
        assert projected.components[0].event_ids == ("verified-transition",)
        assert tuple(store.events()) == before
    finally:
        if adapter == "sqlite":
            store.close()
    if adapter == "sqlite":
        with SQLitePersistence(path) as recovered:
            assert observe(definition(), recovered, catalog=catalog) == projected


@pytest.mark.parametrize("adapter", ("memory", "sqlite"))
@pytest.mark.parametrize("missing", ("trigger", "from_state", "to_state"))
def test_malformed_statechart_payload_is_never_reported_as_evidence(adapter, missing, tmp_path):
    """A forged transition shell cannot be promoted by owner/type alone."""
    path = tmp_path / ("malformed-" + missing + ".sqlite")
    store = MemoryPersistence() if adapter == "memory" else SQLitePersistence(path)
    catalog = builtin_catalog()
    kind = registered_type(catalog, "warehouse_fulfillment", "FulfillmentOrderChart")
    payload = {"trigger": "assign", "from_state": "eligible", "to_state": "active"}
    payload.pop(missing)
    try:
        append(store, owner="org:a", kind=kind, event_id="forged", payload=payload)
        immutable = tuple(store.events())
        with pytest.raises(ValueError, match="malformed observed StateChart transition"):
            observe(definition(), store, catalog=catalog)
        assert tuple(store.events()) == immutable
    finally:
        if adapter == "sqlite":
            store.close()
