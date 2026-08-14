"""Plan → Graph 변환 + 대규모 파이프라인 실행 테스트."""
from __future__ import annotations

import pytest

from dag_langgraph.executor import GraphError, build, run, validate
from dag_langgraph.planner import plan


@pytest.mark.unit
def test_financial_pipeline_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("애플 주식 분석해줘")
    final = run(p)
    
    assert "financial_data" in final
    assert "news_sentiment" in final
    assert "swot_matrix" in final
    assert "full_report" in final
    assert "translated_report_ko" in final
    assert "action_items" in final
    assert len(final["action_items"]) > 0


@pytest.mark.unit
def test_unknown_node_rejected() -> None:
    p = plan("애플 분석")
    p.selected.append("ghost_node")
    with pytest.raises(GraphError, match="알 수 없는 노드"):
        build(p)


@pytest.mark.unit
def test_cycle_rejected_at_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("애플 주식 분석해줘")
    # p.selected 내에 있는 노드로 역방향 엣지 추가하여 사이클 생성
    # search_web_news -> ... -> generate_full_report -> search_web_news
    p.edges.append(("generate_full_report", "search_web_news"))
    with pytest.raises(GraphError, match="사이클"):
        validate(p)


@pytest.mark.unit
def test_auto_start_end_wiring() -> None:
    p = plan("애플 분석")
    g = build(p)
    assert any(src == "__start__" for src, _ in g.edges)
    assert any(dst == "__end__" for _, dst in g.edges)
