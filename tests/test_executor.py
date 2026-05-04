"""Plan → Graph 변환 + 실행 테스트."""
from __future__ import annotations

import pytest

from dag_langgraph.executor import GraphError, build, run, validate
from dag_langgraph.planner import Plan, PlanStep

_ORDER = {
    "order_id": "ORD-TEST",
    "items": [{"sku": "ITEM-A", "qty": 1, "price": 10000}],
    "payment_method": "card",
    "customer_email": "test@example.com",
    "shipping_address": {"city": "Seoul", "zip": "00000", "street": "Test St"},
}


@pytest.mark.unit
def test_full_order_pipeline() -> None:
    """전체 주문 처리 DAG가 정상 실행되는지 확인."""
    p = Plan(
        thought="전체 주문 처리",
        initial_state=_ORDER,
        selected=[
            "validate_order", "check_inventory", "verify_payment",
            "reserve_inventory", "charge_payment",
            "create_shipment", "send_notification", "update_analytics",
        ],
        edges=[
            ("validate_order", "check_inventory"),
            ("validate_order", "verify_payment"),
            ("check_inventory", "reserve_inventory"),
            ("verify_payment", "charge_payment"),
            ("reserve_inventory", "create_shipment"),
            ("charge_payment", "create_shipment"),
            ("create_shipment", "send_notification"),
            ("create_shipment", "update_analytics"),
        ],
    )
    final = run(p)
    assert final["order_valid"] is True
    assert final["shipment_ok"] is True
    assert final["notification_sent"] is True
    assert final["analytics_updated"] is True


@pytest.mark.unit
def test_inventory_only_pipeline() -> None:
    """재고 확인만 하는 단순 파이프라인."""
    p = Plan(
        thought="재고만 확인",
        initial_state=_ORDER,
        selected=["validate_order", "check_inventory"],
        edges=[("validate_order", "check_inventory")],
    )
    final = run(p)
    assert final["order_valid"] is True
    assert final["inventory_ok"] is True
    assert "shipment_id" not in final


@pytest.mark.unit
def test_discount_pipeline() -> None:
    """할인 쿠폰 경로: apply_discount → charge_payment 에서 금액 차감."""
    p = Plan(
        thought="할인 쿠폰 경로",
        initial_state={**_ORDER, "coupon_code": "SAVE10"},
        selected=[
            "validate_order", "check_inventory", "apply_discount",
            "verify_payment", "reserve_inventory", "charge_payment",
            "create_shipment", "send_notification",
        ],
        edges=[
            ("validate_order", "check_inventory"),
            ("validate_order", "apply_discount"),
            ("apply_discount", "verify_payment"),
            ("check_inventory", "reserve_inventory"),
            ("verify_payment", "charge_payment"),
            ("reserve_inventory", "create_shipment"),
            ("charge_payment", "create_shipment"),
            ("create_shipment", "send_notification"),
        ],
    )
    final = run(p)
    assert final["discount_amount"] == pytest.approx(1000.0)
    assert final["charged_amount"] == pytest.approx(9000.0)
    assert final["shipment_ok"] is True


@pytest.mark.unit
def test_unknown_node_rejected() -> None:
    p = Plan(thought="", initial_state={}, selected=["ghost_node"], edges=[])
    with pytest.raises(GraphError, match="알 수 없는 노드"):
        build(p)


@pytest.mark.unit
def test_edge_outside_selected_rejected() -> None:
    with pytest.raises(ValueError, match="selected 외부"):
        Plan(
            thought="",
            initial_state={},
            selected=["validate_order"],
            edges=[("validate_order", "create_shipment")],
        )


@pytest.mark.unit
def test_cycle_rejected_at_validate() -> None:
    p = Plan(
        thought="",
        initial_state={},
        selected=["check_inventory", "verify_payment"],
        edges=[
            ("check_inventory", "verify_payment"),
            ("verify_payment", "check_inventory"),
        ],
    )
    with pytest.raises(GraphError, match="사이클"):
        validate(p)


@pytest.mark.unit
def test_auto_start_end_wiring() -> None:
    p = Plan(
        thought="",
        initial_state=_ORDER,
        selected=["validate_order"],
        edges=[],
    )
    g = build(p)
    assert ("__start__", "validate_order") in g.edges
    assert ("validate_order", "__end__") in g.edges
