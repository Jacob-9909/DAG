"""Graph builder (add_node/add_edge/compile) 테스트."""
from __future__ import annotations

import pytest

from dag_langgraph.graph import END, START, Graph, GraphError


def _echo(key: str, value: str):
    def fn(state):
        return {key: value}
    return fn


@pytest.mark.unit
def test_add_node_and_edge_compile_run() -> None:
    g = Graph()
    g.add_node("a", _echo("x", "A"))
    g.add_node("b", _echo("y", "B"))
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    final = g.compile().invoke()
    assert final == {"x": "A", "y": "B"}


@pytest.mark.unit
def test_initial_state_flows_through() -> None:
    def reader(state):
        return {"echoed": state["seed"]}

    g = Graph()
    g.add_node("r", reader)
    g.set_entry_point("r")
    g.set_finish_point("r")
    final = g.compile().invoke(initial_state={"seed": 42})
    assert final["echoed"] == 42


@pytest.mark.unit
def test_compile_rejects_cycle() -> None:
    g = Graph()
    g.add_node("a", _echo("k", "v"))
    g.add_node("b", _echo("k", "v"))
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    with pytest.raises(GraphError, match="사이클"):
        g.compile()


@pytest.mark.unit
def test_duplicate_id_rejected() -> None:
    g = Graph()
    g.add_node("a", _echo("k", "v"))
    with pytest.raises(GraphError, match="중복"):
        g.add_node("a", _echo("k", "v"))


@pytest.mark.unit
def test_reserved_id_rejected() -> None:
    g = Graph()
    with pytest.raises(GraphError, match="예약"):
        g.add_node(START, _echo("k", "v"))


@pytest.mark.unit
def test_unknown_edge_node_rejected() -> None:
    g = Graph()
    g.add_node("a", _echo("k", "v"))
    g.add_edge("a", "ghost")
    with pytest.raises(GraphError, match="edge dst"):
        g.compile()


@pytest.mark.unit
def test_node_must_return_dict() -> None:
    g = Graph()
    g.add_node("a", lambda s: "not a dict")  # type: ignore[arg-type]
    g.set_entry_point("a")
    g.set_finish_point("a")
    with pytest.raises(GraphError, match="dict 반환"):
        g.compile().invoke()
