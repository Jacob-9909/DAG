"""Plan → Graph 변환 + 실행 테스트."""
from __future__ import annotations

import pytest

from flow_gen.executor import GraphError, build, run, validate
from flow_gen.planner import Plan


@pytest.mark.unit
def test_stub_weather_flow() -> None:
    p = Plan(
        thought="",
        initial_state={"city": "Seoul"},
        selected=["fetch_weather", "summarize_weather", "translate_en"],
        edges=[
            ("fetch_weather", "summarize_weather"),
            ("summarize_weather", "translate_en"),
        ],
    )
    final = run(p)
    assert final["weather"]["city"] == "Seoul"
    assert "Seoul" in final["summary"]
    assert final["translated"].startswith("[en]")


@pytest.mark.unit
def test_unknown_node_rejected() -> None:
    p = Plan(thought="", initial_state={}, selected=["ghost"], edges=[])
    with pytest.raises(GraphError, match="알 수 없는 노드"):
        build(p)


@pytest.mark.unit
def test_edge_outside_selected_rejected() -> None:
    p = Plan(
        thought="",
        initial_state={"city": "X"},
        selected=["fetch_weather"],
        edges=[("fetch_weather", "translate_en")],
    )
    with pytest.raises(GraphError, match="selected 외부"):
        build(p)


@pytest.mark.unit
def test_cycle_rejected_at_validate() -> None:
    p = Plan(
        thought="",
        initial_state={},
        selected=["summarize_weather", "translate_en"],
        edges=[
            ("summarize_weather", "translate_en"),
            ("translate_en", "summarize_weather"),
        ],
    )
    with pytest.raises(GraphError, match="사이클"):
        validate(p)


@pytest.mark.unit
def test_auto_start_end_wiring() -> None:
    p = Plan(
        thought="",
        initial_state={"expr": "1+1"},
        selected=["calc"],
        edges=[],
    )
    g = build(p)
    assert ("__start__", "calc") in g.edges
    assert ("calc", "__end__") in g.edges
