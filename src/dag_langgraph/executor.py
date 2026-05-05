"""Plan → Graph 변환 + 실행. planner와 graph 사이의 다리 역할."""
from __future__ import annotations

from typing import Any

from dag_langgraph.graph import END, START, CompiledGraph, Graph, GraphError
from dag_langgraph.nodes import NODES
from dag_langgraph.planner import Plan


def build(plan: Plan) -> Graph:
    """Plan을 받아 실행 가능한 Graph 객체를 만든다.

    1. Plan.selected에 있는 노드만 NODES 레지스트리에서 꺼내 등록
    2. Plan.edges를 그대로 그래프 엣지로 연결
    3. 진입 엣지가 없는 노드 → START 자동 연결
       진출 엣지가 없는 노드 → END 자동 연결
    """
    g = Graph()
    selected = set(plan.selected)

    # selected 노드를 레지스트리에서 꺼내 그래프에 등록
    for name in plan.selected:
        if name not in NODES:
            raise GraphError(f"알 수 없는 노드: {name}")
        g.add_node(name, NODES[name].fn)

    # Planner가 결정한 엣지를 그대로 그래프에 연결
    for src, dst in plan.edges:
        if src not in selected or dst not in selected:
            raise GraphError(f"edge {src}->{dst} 는 selected 외부 노드 참조")
        g.add_edge(src, dst)

    # 루트 노드(들어오는 엣지 없음) → START 자동 연결
    # 리프 노드(나가는 엣지 없음) → END 자동 연결
    # 덕분에 Planner는 START/END를 신경 쓰지 않아도 된다
    has_incoming = {dst for _s, dst in plan.edges}
    has_outgoing = {src for src, _d in plan.edges}
    for name in plan.selected:
        if name not in has_incoming:
            g.add_edge(START, name)
        if name not in has_outgoing:
            g.add_edge(name, END)
    return g


def compile(plan: Plan) -> CompiledGraph:
    """Plan → Graph 조립 → LangGraph 컴파일까지 한 번에 처리한다."""
    return build(plan).compile()


def run(plan: Plan, verbose: bool = False) -> dict[str, Any]:
    """Plan을 받아 그래프를 실행하고 최종 state를 반환한다."""
    return compile(plan).invoke(initial_state=plan.initial_state, verbose=verbose)


def validate(plan: Plan) -> None:
    """Plan의 그래프 구조가 유효한지 검증만 한다 (실행 없음). 사이클·미존재 노드 등 탐지."""
    compile(plan)


__all__ = ["GraphError", "build", "compile", "run", "validate"]
