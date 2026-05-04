"""노드 레지스트리 + 개별 노드 동작."""
from __future__ import annotations

import pytest

from dag_langgraph.nodes import NODES, descriptions

_ORDER = {
    "order_id": "ORD-001",
    "items": [{"sku": "ITEM-1", "qty": 2, "price": 5000}],
    "payment_method": "card",
    "customer_email": "test@example.com",
    "shipping_address": {"city": "Seoul", "zip": "12345", "street": "Main St"},
}


@pytest.mark.unit
def test_registry_non_empty_and_unique() -> None:
    names = [d["name"] for d in descriptions()]
    assert len(names) == len(set(names))
    assert "validate_order" in NODES
    assert "create_shipment" in NODES


@pytest.mark.unit
def test_validate_order_passes_with_full_state() -> None:
    out = NODES["validate_order"].fn(_ORDER)
    assert out["order_valid"] is True
    assert out["validation_errors"] == []


@pytest.mark.unit
def test_validate_order_fails_on_missing_field() -> None:
    state = {k: v for k, v in _ORDER.items() if k != "customer_email"}
    out = NODES["validate_order"].fn(state)
    assert out["order_valid"] is False
    assert "customer_email" in out["validation_errors"]


@pytest.mark.unit
def test_check_inventory_returns_stock_per_sku() -> None:
    out = NODES["check_inventory"].fn(_ORDER)
    assert "ITEM-1" in out["stock_levels"]
    assert out["inventory_ok"] is True


@pytest.mark.unit
def test_verify_payment_accepts_card() -> None:
    out = NODES["verify_payment"].fn(_ORDER)
    assert out["payment_valid"] is True


@pytest.mark.unit
def test_verify_payment_rejects_unknown_method() -> None:
    out = NODES["verify_payment"].fn({**_ORDER, "payment_method": "bitcoin"})
    assert out["payment_valid"] is False


@pytest.mark.unit
def test_apply_discount_known_coupon() -> None:
    out = NODES["apply_discount"].fn({**_ORDER, "coupon_code": "SAVE10"})
    assert out["discount_rate"] == 0.10
    assert out["discount_amount"] == pytest.approx(1000.0)


@pytest.mark.unit
def test_reserve_inventory_requires_inventory_ok() -> None:
    out = NODES["reserve_inventory"].fn({**_ORDER, "inventory_ok": False})
    assert out["reservation_ok"] is False
    assert out["reservation_id"] is None


@pytest.mark.unit
def test_charge_payment_deducts_discount() -> None:
    state = {**_ORDER, "payment_valid": True, "discount_amount": 1000.0}
    out = NODES["charge_payment"].fn(state)
    assert out["charge_ok"] is True
    assert out["charged_amount"] == pytest.approx(9000.0)


@pytest.mark.unit
def test_create_shipment_requires_both_reserve_and_charge() -> None:
    state = {**_ORDER, "reservation_ok": True, "charge_ok": False}
    out = NODES["create_shipment"].fn(state)
    assert out["shipment_ok"] is False


@pytest.mark.unit
def test_full_happy_path_state_flow() -> None:
    """각 노드를 순서대로 수동 실행해 state가 올바르게 누적되는지 확인."""
    state: dict = dict(_ORDER)

    state.update(NODES["validate_order"].fn(state))
    state.update(NODES["check_inventory"].fn(state))
    state.update(NODES["verify_payment"].fn(state))
    state.update(NODES["reserve_inventory"].fn(state))
    state.update(NODES["charge_payment"].fn(state))
    state.update(NODES["create_shipment"].fn(state))
    state.update(NODES["send_notification"].fn(state))
    state.update(NODES["update_analytics"].fn(state))

    assert state["order_valid"] is True
    assert state["inventory_ok"] is True
    assert state["payment_valid"] is True
    assert state["reservation_ok"] is True
    assert state["charge_ok"] is True
    assert state["shipment_ok"] is True
    assert state["notification_sent"] is True
    assert state["analytics_updated"] is True
