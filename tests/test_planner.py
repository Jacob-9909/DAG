"""Planner stub + 카탈로그 검증."""
from __future__ import annotations

import pytest

from dag_langgraph.nodes import NODES
from dag_langgraph.planner import Plan, plan


@pytest.mark.unit
def test_stub_plan_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("서울 날씨 알려줘")
    assert isinstance(p, Plan)
    assert all(name in NODES for name in p.selected)
    assert p.steps
    assert isinstance(p.parallel, list)


@pytest.mark.unit
def test_stub_plan_calc_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("2+3 계산해줘")
    assert p.selected == ["calc"]
    assert p.steps[0].tasks == ["calc"]


@pytest.mark.unit
def test_stub_plan_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("AI news 검색해줘")
    assert "search_web" in p.selected
    assert len(p.steps) == 2


@pytest.mark.unit
def test_plan_validation_rejects_unknown_parallel_node() -> None:
    with pytest.raises(ValueError, match="parallel 그룹에 selected 외부 노드 포함"):
        Plan(
            thought="",
            initial_state={},
            selected=["calc"],
            edges=[],
            steps=[],
            parallel=[["calc", "ghost"]],
        )
