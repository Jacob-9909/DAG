"""Graph builder backed by LangGraph. 공유 state dict 기반.

사용 패턴:
    g = Graph()
    g.add_node("a", fn_a)   # fn: (state) -> state_update
    g.add_node("b", fn_b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    compiled = g.compile()
    final = compiled.invoke(initial_state={"city": "Seoul"})
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

State = dict[str, Any]
NodeFn = Callable[[State], State]


class GraphError(Exception):
    """DAG 구조 오류."""


@dataclass(frozen=True)
class NodeSpec:
    name: str
    fn: NodeFn


@dataclass(frozen=True)
class CompiledGraph:
    order: tuple[str, ...]
    nodes: dict[str, NodeSpec]
    adj: dict[str, tuple[str, ...]]
    _runnable: Any = field(repr=False, hash=False, compare=False)

    def invoke(self, initial_state: State | None = None, verbose: bool = False) -> State:
        if verbose:
            logger.info("LangGraph invoke start (state keys=%s)", list(initial_state or {}))
        final = self._runnable.invoke(dict(initial_state or {}))
        if not isinstance(final, dict):
            raise GraphError(f"graph invoke 결과는 dict 여야 함, got {type(final).__name__}")
        if verbose:
            logger.info("LangGraph invoke done (state keys=%s)", list(final))
        return final


class Graph:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeSpec] = {}
        self._edges: set[tuple[str, str]] = set()

    def add_node(self, name: str, fn: NodeFn) -> Graph:
        if name in (START, END):
            raise GraphError(f"예약된 id: {name}")
        if name in self._nodes:
            raise GraphError(f"중복 node id: {name}")
        self._nodes[name] = NodeSpec(name=name, fn=fn)
        return self

    def add_edge(self, src: str, dst: str) -> Graph:
        self._edges.add((src, dst))
        return self

    def set_entry_point(self, name: str) -> Graph:
        return self.add_edge(START, name)

    def set_finish_point(self, name: str) -> Graph:
        return self.add_edge(name, END)

    def compile(self) -> CompiledGraph:
        self._validate_edges()
        adj = self._adjacency()
        order = self._topo_order(adj)

        sg = StateGraph(dict)
        for name, spec in self._nodes.items():
            sg.add_node(name, self._validated_node_fn(name, spec.fn))
        for src, dst in self._edges:
            sg.add_edge(src, dst)
        runnable = sg.compile()

        return CompiledGraph(
            order=tuple(order),
            nodes=dict(self._nodes),
            adj={k: tuple(v) for k, v in adj.items()},
            _runnable=runnable,
        )

    def _validated_node_fn(self, name: str, fn: NodeFn) -> Callable[[State], State]:
        def wrapped(state: State) -> State:
            update = fn(state)
            if not isinstance(update, dict):
                raise GraphError(f"{name} 는 dict 반환 필요, got {type(update).__name__}")
            # 기존 엔진과 동일하게 "누적 state + update" semantics를 유지한다.
            return {**state, **update}

        return wrapped

    def _validate_edges(self) -> None:
        ids = set(self._nodes) | {START, END}
        for src, dst in self._edges:
            if src not in ids:
                raise GraphError(f"edge src 미존재: {src}")
            if dst not in ids:
                raise GraphError(f"edge dst 미존재: {dst}")

    def _adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        for src, dst in self._edges:
            adj[src].append(dst)
        return adj

    def _topo_order(self, adj: dict[str, list[str]]) -> list[str]:
        all_ids = set(self._nodes) | {START, END}
        indeg: dict[str, int] = dict.fromkeys(all_ids, 0)
        for _src, dst in self._edges:
            indeg[dst] += 1
        q: deque[str] = deque([x for x, v in indeg.items() if v == 0])
        order: list[str] = []
        while q:
            x = q.popleft()
            order.append(x)
            for y in adj.get(x, ()):
                indeg[y] -= 1
                if indeg[y] == 0:
                    q.append(y)
        if len(order) != len(all_ids):
            raise GraphError("사이클 탐지됨")
        return order

    @property
    def edges(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._edges)
