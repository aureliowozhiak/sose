"""Restartable OD-5a *boundary* reconciliation over committed physical events.

This adapter does not execute SimPy processes, advance the source scheduler,
or mint physical events. It advances one existing authoritative boundary
transition per invocation: publish -> claim -> ACK/Command -> apply -> certify.
Every phase is separately committed, so OS death/response loss can resume
from stored semantics, not from local volatile worker memory.

This is an operational pilot, not production OD-5a scientific admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sose.composition.boundary import (
    BoundaryLease, BoundaryService, StaleBoundaryClaimError,
)
from sose.composition.model import BoundaryDelivery, BoundaryMessage, DeliveryStatus
from sose.core.identity import deterministic_id
from sose.persistence.base import Persistence

from .od5a_boundary import (
    _CONTRACT, _DESTINATION, _SOURCE, _VERSION, _physical_event,
    consume_od5a_physical_completion, publish_od5a_physical_completion,
)
from .od5a_observation import (
    _verified_intent, _verified_observation, _verified_prior_certificate,
    _verify_receipt, apply_od5a_physical_observation,
    certify_od5a_physical_observation,
)


@dataclass(frozen=True)
class OD5aBoundaryStep:
    phase: str
    event_id: str | None = None
    message_id: str | None = None

    def __post_init__(self) -> None:
        if self.phase not in {
            "published", "claimed", "acknowledged", "applied",
            "certified", "blocked", "idle",
        }:
            raise ValueError("unknown OD-5a boundary phase")


def _canonical_message(job_id, event, payload):
    return BoundaryMessage.create(
        contract_name=_CONTRACT, contract_version=_VERSION,
        source_domain=_SOURCE, source_identity=job_id,
        destination_domain=_DESTINATION, occurrence_key=event.event_id,
        correlation_id=job_id, causation_id=event.event_id,
        causation_kind="event", produced_at=event.occurred_at,
        payload=payload,
    )


def reconcile_od5a_boundary_once(
    store: Persistence, *, job_id: str, owner_id: str,
    now: datetime, lease_duration: timedelta,
) -> OD5aBoundaryStep:
    """Make at most one durable causal step for one organization.

    The worker may be destroyed between *any* two calls. A live claim is
    owned only by the holder; other workers can reclaim it after expiry.
    Independent organizations may progress without a synthetic shared clock.
    """
    if not job_id or not owner_id:
        raise ValueError("OD-5a reconciler needs a job and worker identity")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("OD-5a boundary now must be timezone aware")
    if lease_duration <= timedelta(0):
        raise ValueError("OD-5a boundary lease must be positive")

    # Discovery is deliberately read-only and may be stale; every authority
    # check is repeated against the current UoW before any mutation.
    candidates = sorted(
        (event for event in store.events()
         if event.entity_type == "od5a_durable_pilot"
         and event.entity_id == job_id
         and event.name in {"od5a.execution.v1", "od5a.coordination.v1"}),
        key=lambda x: (x.occurred_at, x.tick if x.tick is not None else -1, x.event_id),
    )
    blocked = False

    for source in candidates:
        if source.occurred_at > now:
            blocked = True
            continue
        with store.transaction() as uow:
            event, physical = _physical_event(
                uow, job_id=job_id, event_id=source.event_id,
            )
            message = _canonical_message(job_id, event, physical)
            existing = uow.get_boundary_message(message.message_id)
            if existing is not None and existing != message:
                raise ValueError("OD-5a boundary canonical message identity conflict")
            delivery_key = BoundaryDelivery.pending(message).delivery_id
            delivery = uow.get_boundary_delivery(delivery_key)
            if existing is None:
                if delivery is not None:
                    raise ValueError("OD-5a boundary delivery lacks committed source message")
                phase = "published"
            elif delivery is None:
                phase = "published"
            elif (
                delivery.delivery_id != delivery_key
                or delivery.message_id != message.message_id
                or delivery.destination_domain != _DESTINATION
                or delivery.contract_name != _CONTRACT
                or delivery.contract_version != _VERSION
            ):
                raise ValueError("OD-5a boundary delivery contradicts source contract")
            elif delivery.status is DeliveryStatus.CONSUMED:
                effect_id = deterministic_id("od5a-physical-command", message.message_id)
                _verify_receipt(
                    uow, message_id=message.message_id, effect_id=effect_id,
                )
                proof = uow.get_business_effect(effect_id)
                if proof is not None:
                    _verified_prior_certificate(uow, effect_id=effect_id, prior=proof)
                    continue
                _, original_event, _, attributes, ack_at = _verified_intent(
                    uow, effect_id=effect_id,
                )
                entity = uow.get_entity("od5a_physical_observation", event.event_id)
                if entity is None:
                    phase = "applied"
                else:
                    _verified_observation(
                        uow, event=original_event, attributes=attributes, ack_at=ack_at,
                    )
                    phase = "certified"
            elif delivery.status is DeliveryStatus.PENDING:
                phase = "claimed"
            elif delivery.status is DeliveryStatus.CLAIMED:
                if (
                    delivery.claim_owner_id == owner_id
                    and delivery.lease_expires_at is not None
                    and delivery.lease_expires_at > now
                ):
                    phase = "acknowledged"
                elif (
                    delivery.lease_expires_at is None
                    or delivery.lease_expires_at <= now
                ):
                    phase = "claimed"
                else:
                    blocked = True
                    continue
            else:
                raise ValueError("unsupported OD-5a delivery status")
            active_lease = (
                BoundaryLease(
                    delivery_id=delivery.delivery_id,
                    message_id=message.message_id,
                    owner_id=owner_id,
                    epoch=delivery.claim_epoch,
                    lease_expires_at=delivery.lease_expires_at,
                ) if phase == "acknowledged" else None
            )
        if phase == "published":
            publish_od5a_physical_completion(
                store, job_id=job_id, event_id=event.event_id,
            )
        elif phase == "claimed":
            lease = BoundaryService(store).claim_next(
                owner_id=owner_id, now=now, lease_duration=lease_duration,
                destination_domain=_DESTINATION,
                accepted_contracts=frozenset({(_CONTRACT, _VERSION)}),
                message_id=message.message_id, correlation_id=job_id,
            )
            if lease is None:
                blocked = True
                continue
        elif phase == "acknowledged":
            try:
                consume_od5a_physical_completion(
                    store, lease=active_lease, now=now,
                )
            except StaleBoundaryClaimError:
                blocked = True
                continue
        elif phase == "applied":
            apply_od5a_physical_observation(
                store, effect_id=effect_id, applied_at=now,
            )
        elif phase == "certified":
            certify_od5a_physical_observation(
                store, effect_id=effect_id, completed_at=now,
            )
        return OD5aBoundaryStep(
            phase=phase, event_id=event.event_id, message_id=message.message_id,
        )

    return OD5aBoundaryStep("blocked" if blocked else "idle")


__all__ = ["OD5aBoundaryStep", "reconcile_od5a_boundary_once"]
