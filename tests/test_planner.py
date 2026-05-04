"""Planner stub + 카탈로그 검증."""
from __future__ import annotations

import pytest

from dag_langgraph.nodes import NODES
from dag_langgraph.planner import Plan, plan


@pytest.mark.unit
def test_stub_plan_default_full_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("주문 처리해줘")
    assert isinstance(p, Plan)
    assert all(name in NODES for name in p.selected)
    # 전체 파이프라인: 8개 노드
    assert "validate_order" in p.selected
    assert "create_shipment" in p.selected
    assert p.steps
    # 병렬 그룹 존재
    assert any(len(g) >= 2 for g in p.parallel)


@pytest.mark.unit
def test_stub_plan_inventory_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("재고 확인만 해줘")
    assert p.selected == ["validate_order", "check_inventory"]
    assert p.steps[0].tasks == ["validate_order"]
    assert p.parallel == []


@pytest.mark.unit
def test_stub_plan_discount_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("할인 쿠폰 적용해서 주문 처리")
    assert "apply_discount" in p.selected
    assert any("apply_discount" in g for g in p.parallel) or \
           any("apply_discount" in step.tasks for step in p.steps)


@pytest.mark.unit
def test_plan_validation_rejects_unknown_parallel_node() -> None:
    with pytest.raises(ValueError, match="parallel 그룹에 selected 외부 노드 포함"):
        Plan(
            thought="",
            initial_state={},
            selected=["validate_order"],
            edges=[],
            steps=[],
            parallel=[["validate_order", "ghost_node"]],
        )
