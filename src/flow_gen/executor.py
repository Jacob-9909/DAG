"""Plan → Graph 변환 + 실행. Planner 는 레지스트리에서 선택만 하므로 executor 가 바인딩."""
from __future__ import annotations

from typing import Any

from flow_gen.graph import END, START, CompiledGraph, Graph, GraphError
from flow_gen.nodes import NODES
from flow_gen.planner import Plan


def build(plan: Plan) -> Graph:
    g = Graph()
    selected = set(plan.selected)

    for name in plan.selected:
        if name not in NODES:
            raise GraphError(f"알 수 없는 노드: {name}")
        g.add_node(name, NODES[name].fn)

    for src, dst in plan.edges:
        if src not in selected or dst not in selected:
            raise GraphError(f"edge {src}->{dst} 는 selected 외부 노드 참조")
        g.add_edge(src, dst)

    # 루트/리프 자동 START/END 연결
    has_incoming = {dst for _s, dst in plan.edges}
    has_outgoing = {src for src, _d in plan.edges}
    for name in plan.selected:
        if name not in has_incoming:
            g.add_edge(START, name)
        if name not in has_outgoing:
            g.add_edge(name, END)
    return g


def compile(plan: Plan) -> CompiledGraph:
    return build(plan).compile()


def run(plan: Plan, verbose: bool = False) -> dict[str, Any]:
    return compile(plan).invoke(initial_state=plan.initial_state, verbose=verbose)


def validate(plan: Plan) -> None:
    compile(plan)


__all__ = ["GraphError", "build", "compile", "run", "validate"]
