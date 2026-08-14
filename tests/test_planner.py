"""Planner stub + 카탈로그 검증 unit 테스트."""
from __future__ import annotations

import pytest

from dag_langgraph.nodes import NODES
from dag_langgraph.planner import Plan, plan


@pytest.mark.unit
def test_stub_plan_financial_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("애플 주식 분석해줘")
    assert isinstance(p, Plan)
    assert all(name in NODES for name in p.selected)
    assert "fetch_financial_data" in p.selected
    assert "synthesize_swot" in p.selected
    assert len(p.selected) >= 10
    assert len(p.steps) == 4
    assert len(p.parallel) >= 3


@pytest.mark.unit
def test_stub_plan_tech_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("최신 AI 기술 논문 및 트렌드 조사")
    assert "fetch_tech_papers" in p.selected
    assert "cluster_tech_trends" in p.selected
    assert len(p.selected) >= 8


@pytest.mark.unit
def test_stub_plan_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("종합 마켓 리서치 보고서 생성해줘")
    assert len(p.selected) >= 8
    assert "generate_full_report" in p.selected


@pytest.mark.unit
def test_plan_validation_rejects_unknown_parallel_node() -> None:
    with pytest.raises(ValueError, match="parallel 그룹에 selected 외부 노드 포함"):
        Plan(
            thought="",
            initial_state={},
            selected=["search_web_news"],
            edges=[],
            steps=[],
            parallel=[["search_web_news", "ghost"]],
        )
