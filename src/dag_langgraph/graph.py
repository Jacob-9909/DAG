"""Graph builder backed by LangGraph. 공유 state dict 기반.

사용 패턴:
    g = Graph()
    g.add_node("a", fn_a)   # fn: (state) -> state_update
    g.add_node("b", fn_b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    compiled = g.compile()
    final = compiled.invoke(initial_state={"order_id": "001", ...})
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

State = dict[str, Any]
NodeFn = Callable[[State], State]

# 병렬 실행 시 여러 노드가 동시에 state를 업데이트할 때 LangGraph가 자동으로 합쳐주는 타입.
# 기본 StateGraph(dict)는 한 스텝에 하나의 업데이트만 허용(LastValue)해서
# fan-in(여러 노드 → 하나의 노드) 구조에서 InvalidUpdateError가 발생한다.
# Annotated의 두 번째 인자(lambda)가 reducer: 두 dict를 받아 하나로 합친다.
_MergeableState = Annotated[dict, lambda a, b: {**a, **b}]


class GraphError(Exception):
    """DAG 구조 오류 (사이클, 미존재 노드, 중복 등)."""


# frozen=True: 컴파일 후 NodeSpec을 변경할 수 없게 한다
@dataclass(frozen=True)
class NodeSpec:
    """등록된 노드 하나를 나타내는 불변 레코드."""
    name: str
    fn: NodeFn


@dataclass(frozen=True)
class CompiledGraph:
    """compile() 결과. 실행 준비가 완료된 그래프."""
    order: tuple[str, ...]             # 위상 정렬된 노드 실행 순서 (디버깅·출력용)
    nodes: dict[str, NodeSpec]         # 등록된 노드 목록
    adj: dict[str, tuple[str, ...]]    # 인접 리스트 (src → [dst, ...])
    _runnable: Any = field(repr=False, hash=False, compare=False)  # LangGraph 내부 객체

    def invoke(self, initial_state: State | None = None, verbose: bool = False) -> State:
        """초기 state를 주입하고 그래프를 끝까지 실행한 뒤 최종 state를 반환한다."""
        if verbose:
            logger.info("LangGraph invoke start (state keys=%s)", list(initial_state or {}))
        # LangGraph runnable에 초기 state를 넘겨 실행
        final = self._runnable.invoke(dict(initial_state or {}))
        if not isinstance(final, dict):
            raise GraphError(f"graph invoke 결과는 dict 여야 함, got {type(final).__name__}")
        if verbose:
            logger.info("LangGraph invoke done (state keys=%s)", list(final))
        return final


class Graph:
    """노드와 엣지를 등록하고 LangGraph StateGraph로 컴파일하는 빌더."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeSpec] = {}
        self._edges: set[tuple[str, str]] = set()

    def add_node(self, name: str, fn: NodeFn) -> Graph:
        """노드를 등록한다. START/END는 LangGraph 예약어라 사용 불가."""
        if name in (START, END):
            raise GraphError(f"예약된 id: {name}")
        if name in self._nodes:
            raise GraphError(f"중복 node id: {name}")
        self._nodes[name] = NodeSpec(name=name, fn=fn)
        return self  # 메서드 체이닝 가능하도록 self 반환

    def add_edge(self, src: str, dst: str) -> Graph:
        """방향성 엣지를 추가한다. src → dst 순서로 실행된다."""
        self._edges.add((src, dst))
        return self

    def set_entry_point(self, name: str) -> Graph:
        """그래프의 시작 노드를 지정한다. START → name 엣지를 추가하는 편의 메서드."""
        return self.add_edge(START, name)

    def set_finish_point(self, name: str) -> Graph:
        """그래프의 종료 노드를 지정한다. name → END 엣지를 추가하는 편의 메서드."""
        return self.add_edge(name, END)

    def compile(self) -> CompiledGraph:
        """등록된 노드·엣지를 검증하고 LangGraph runnable로 변환한다."""
        self._validate_edges()         # 엣지가 존재하는 노드만 참조하는지 확인
        adj = self._adjacency()        # 인접 리스트 생성
        order = self._topo_order(adj)  # Kahn 알고리즘으로 위상 정렬 + 사이클 탐지

        # LangGraph StateGraph 조립
        sg = StateGraph(_MergeableState)  # 병렬 fan-in 허용 state 타입 사용
        for name, spec in self._nodes.items():
            # 노드 함수를 검증 래퍼로 감싸서 등록
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
        """노드 함수를 감싸 반환값이 dict인지 검증한다.

        노드는 변경된 키만 담은 부분 업데이트를 반환해야 한다.
        _MergeableState reducer가 기존 state와 자동으로 합쳐준다.
        """
        def wrapped(state: State) -> State:
            update = fn(state)
            if not isinstance(update, dict):
                raise GraphError(f"{name} 는 dict 반환 필요, got {type(update).__name__}")
            # 전체 state가 아닌 업데이트된 키만 반환 → reducer가 기존 state에 merge
            return update

        return wrapped

    def _validate_edges(self) -> None:
        """엣지의 출발·도착 노드가 모두 등록된 노드인지 확인한다."""
        ids = set(self._nodes) | {START, END}
        for src, dst in self._edges:
            if src not in ids:
                raise GraphError(f"edge src 미존재: {src}")
            if dst not in ids:
                raise GraphError(f"edge dst 미존재: {dst}")

    def _adjacency(self) -> dict[str, list[str]]:
        """엣지 집합을 인접 리스트(src → [dst, ...])로 변환한다."""
        adj: dict[str, list[str]] = defaultdict(list)
        for src, dst in self._edges:
            adj[src].append(dst)
        return adj

    def _topo_order(self, adj: dict[str, list[str]]) -> list[str]:
        """Kahn 알고리즘으로 위상 정렬을 수행한다.

        진입 차수(in-degree)가 0인 노드부터 큐에 넣고,
        처리할 때마다 이웃 노드의 진입 차수를 1씩 줄인다.
        모든 노드를 처리하지 못하면 사이클이 있다는 의미.
        """
        all_ids = set(self._nodes) | {START, END}
        # 각 노드의 진입 차수(들어오는 엣지 수) 초기화
        indeg: dict[str, int] = dict.fromkeys(all_ids, 0)
        for _src, dst in self._edges:
            indeg[dst] += 1
        # 진입 차수가 0인 노드(선행 노드가 없는 노드)부터 큐에 삽입
        q: deque[str] = deque([x for x, v in indeg.items() if v == 0])
        order: list[str] = []
        while q:
            x = q.popleft()
            order.append(x)
            for y in adj.get(x, ()):
                indeg[y] -= 1
                # 진입 차수가 0이 된 노드는 이제 실행 가능 → 큐에 추가
                if indeg[y] == 0:
                    q.append(y)
        # 처리된 노드 수가 전체보다 적으면 사이클 존재
        if len(order) != len(all_ids):
            raise GraphError("사이클 탐지됨")
        return order

    @property
    def edges(self) -> frozenset[tuple[str, str]]:
        """등록된 엣지 집합 (읽기 전용)."""
        return frozenset(self._edges)
