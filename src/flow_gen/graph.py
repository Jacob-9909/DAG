"""Graph builder (LangGraph-style). 공유 state dict 기반.

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
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

START = "__start__"
END = "__end__"

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

    def invoke(self, initial_state: State | None = None, verbose: bool = False) -> State:
        state: State = dict(initial_state or {})
        for nid in self.order:
            if nid in (START, END):
                continue
            spec = self.nodes[nid]
            if verbose:
                logger.info("run %s (state keys=%s)", nid, list(state))
            update = spec.fn(state)
            if not isinstance(update, dict):
                raise GraphError(f"{nid} 는 dict 반환 필요, got {type(update).__name__}")
            state.update(update)
            if verbose:
                logger.info("  -> update=%s", update)
        return state


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
        return CompiledGraph(
            order=tuple(order),
            nodes=dict(self._nodes),
            adj={k: tuple(v) for k, v in adj.items()},
        )

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

    # CLI 편의 접근자
    @property
    def edges(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._edges)
