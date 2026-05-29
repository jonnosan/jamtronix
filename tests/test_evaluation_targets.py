"""Sanity tests for the Target dataclass + ANCHORS registry."""

from __future__ import annotations

from jtx.evaluation import ANCHORS, DeliveryCheck, IntentCheck, Target


def test_anchors_registry_has_expected_names() -> None:
    assert set(ANCHORS.keys()) == {
        "acid", "deep_techno", "psytrance", "dub_techno",
        "happy", "sad", "brooding",
    }


def test_each_anchor_has_at_least_one_intent_and_delivery_check() -> None:
    for name, target in ANCHORS.items():
        assert target.name == name
        assert len(target.intent_predicates) >= 1, name
        assert len(target.delivery_descriptors) >= 1, name


def test_target_dataclass_is_frozen() -> None:
    target = ANCHORS["acid"]
    try:
        target.name = "mutated"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Target should be frozen")


def test_intent_and_delivery_check_labels_are_unique_within_target() -> None:
    for name, target in ANCHORS.items():
        intent_labels = [ic.label for ic in target.intent_predicates]
        delivery_labels = [dc.label for dc in target.delivery_descriptors]
        assert len(intent_labels) == len(set(intent_labels)), f"{name} intent labels collide"
        assert len(delivery_labels) == len(set(delivery_labels)), f"{name} delivery labels collide"


def test_custom_target_construction_works() -> None:
    """The Target API is meant to be extensible — users can declare their own."""
    custom = Target(
        name="my_anchor",
        intent_predicates=(IntentCheck("always 1", lambda song: 1.0),),
        delivery_descriptors=(DeliveryCheck("always 1", lambda sample: 1.0),),
    )
    assert custom.name == "my_anchor"
