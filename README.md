# flow-gen

Dynamic DAG / Flow Generation agent orchestrator.

**설계:**
- 노드는 `nodes.py` 레지스트리에 **미리 정의**됨 (이름 + 설명 + 구현)
- Planner(LLM)는 카탈로그 설명만 보고 필요한 **노드를 선택** + **엣지를 결정**
- 노드 구현/params 는 Planner 가 건드리지 않는다
- 데이터 흐름: 공유 `state` dict (LangGraph 스타일). 각 노드 `fn(state) -> state_update`.

## 흐름

```
유저 목표
  ↓ (카탈로그 descriptions 프롬프트 주입)
Planner → Plan JSON {thought, initial_state, selected, edges}
  ↓
executor.build(plan):
    for name in selected: g.add_node(name, NODES[name].fn)
    for src, dst in edges: g.add_edge(src, dst)
    # in-edge 없음 → START→node, out-edge 없음 → node→END 자동
  ↓
g.compile() → CompiledGraph (검증 + 위상정렬)
  ↓
compiled.invoke(initial_state) → 최종 state dict
```

## 구조

```
.
├── pyproject.toml
├── src/flow_gen/
│   ├── __init__.py
│   ├── nodes.py        # Node dataclass + NODES 레지스트리 (사전 정의)
│   ├── graph.py        # Graph 빌더 (add_node/add_edge/compile/invoke)
│   ├── planner.py      # LLM → Plan (selected + edges). 키 없으면 stub
│   ├── executor.py     # Plan → Graph 변환 + run 파사드
│   └── cli.py          # `flow-gen` entrypoint
└── tests/
    ├── test_graph.py
    ├── test_nodes.py
    ├── test_planner.py
    └── test_executor.py
```

## Setup

```bash
uv sync --extra dev
cp .env.example .env        # ANTHROPIC_API_KEY (선택, 없으면 stub)
```

## Run

```bash
uv run flow-gen "서울 날씨 알려줘"
uv run flow-gen --list-nodes          # 카탈로그 확인
uv run flow-gen -v "..."              # verbose (단계별 state 변화)
```

## Test

```bash
uv run pytest
uv run pytest --cov=src --cov-report=term-missing
```

## Graph API 직접 사용 (노드 직접 바인딩)

```python
from flow_gen import Graph, START, END, NODES

g = Graph()
g.add_node("fetch_weather", NODES["fetch_weather"].fn)
g.add_node("summarize_weather", NODES["summarize_weather"].fn)
g.set_entry_point("fetch_weather")
g.add_edge("fetch_weather", "summarize_weather")
g.set_finish_point("summarize_weather")

state = g.compile().invoke(initial_state={"city": "Busan"})
```

## 새 노드 추가

[src/flow_gen/nodes.py](src/flow_gen/nodes.py) 의 `_REGISTRY` 에 `Node(name, description, fn)` 추가.
설명에 **읽는 state 키** + **쓰는 state 키** 명시. Planner 는 이 설명만으로 연결 가능성을 판단한다.

## 설계 포인트

| 개념 | 위치 |
|---|---|
| 사전 정의된 노드 | `nodes.NODES` (카탈로그 + 설명) |
| Planner 역할 제한 | 선택 + 엣지만. 구현/params 불가 |
| Pydantic 스키마 강제 | `planner.Plan` |
| Builder API | `graph.Graph` (add_node/add_edge) |
| 사이클 탐지 + 위상정렬 (Kahn) | `graph.Graph._topo_order` |
| 공유 state 데이터 흐름 | `graph.CompiledGraph.invoke` |
| Plan → Graph 변환 | `executor.build` |
| Stub fallback | `planner._stub_plan` |
