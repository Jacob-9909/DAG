# flow-gen

Dynamic Multi-Stage Deep Research & Analytics DAG Orchestrator.

**설계:**
- 노드는 [`nodes.py`](src/dag_langgraph/nodes.py) 레지스트리에 **독립적 효용성을 갖춘 16개 모듈**로 정의됨 (이름 + 상세 명세 + 구현)
- Planner(LLM)는 카탈로그 설명만 보고 필요한 **노드 선택** + **다단계 의존성 엣지 및 병렬 그룹 결정**
- 노드 구현/params 는 Planner가 건드리지 않는다
- 데이터 흐름: 공유 `state` dict (LangGraph StateSchema 병합 래퍼 기반). 각 노드 `fn(state) -> state_update`.

---

## 1. 아키텍처 & 실행 흐름

```mermaid
flowchart TD
    User["유저 목표 (Goal)\n예: 애플 주식 분석 및 리포트 작성"] --> Planner["Planner (LLM)\n- 16개 카탈로그 명세 참조\n- Selected, Edges, Parallel 그룹 결정"]
    Planner --> PlanJSON["Plan JSON\n{initial_state, selected, edges, steps, parallel}"]
    PlanJSON --> Executor["Executor (Graph Builder)\n- Selected 노드 바인딩 & Edges 수동 구성\n- in/out-edge 없는 노드 START/END 자동 보정"]
    Executor --> Compile["CompiledGraph\n- LangGraph StateSchema 컴파일\n- 사이클 탐지 & Kahn 위상 정렬"]
    Compile --> Invoke["CompiledGraph.invoke()\n- 공유 State dict 기반 단계별 누적 실행"]
    Invoke --> FinalState["최종 State dict\n(종합 리포트, SWOT, Action Item, 번역 등)"]
```

---

## 2. 대표 DAG 파이프라인 다이어그램 (11-Node Enterprise Intelligence Flow)

유저가 `"애플 주식 분석 및 최근 뉴스 리포트 작성해줘"`를 입력했을 때 동적으로 생성되어 실행되는 다단계 DAG 구조입니다.

```mermaid
graph TD
    subgraph Step1["Step 1: 멀티소스 병렬 데이터 수집 (Ingestion)"]
        START["__START__"] --> N1["search_web_news<br/>(뉴스 수집)"]
        START --> N2["fetch_financial_data<br/>(재무 지표 수집)"]
        START --> N3["fetch_community_sentiment<br/>(커뮤니티 트렌드 수집)"]
    end

    subgraph Step2["Step 2: 심층 인텔리전스 분석 (Analysis)"]
        N1 --> N4["analyze_news_sentiment<br/>(감성 점수 연산)"]
        N1 --> N5["extract_risks_and_opportunities<br/>(리스크 & 기회 추출)"]
        N2 --> N5
        N2 --> N6["calculate_financial_ratios<br/>(재무 비율 & 밸류에이션)"]
    end

    subgraph Step3["Step 3: SWOT & 요약 종합 (Synthesis)"]
        N4 --> N7["synthesize_swot<br/>(SWOT 매트릭스 작성)"]
        N5 --> N7
        N6 --> N7
        N4 --> N8["generate_executive_summary<br/>(경영진 3줄 요약)"]
        N6 --> N8
        N7 --> N9["generate_full_report<br/>(종합 마크다운 리포트)"]
        N8 --> N9
    end

    subgraph Step4["Step 4: 후처리 & 액션 가공 (Publishing)"]
        N7 --> N10["extract_action_items<br/>(우선순위 실행과제 추출)"]
        N9 --> N11["translate_report_ko<br/>(한국어 리포트 정제/번역)"]
        N3 --> END["__END__"]
        N10 --> END
        N11 --> END
    end

    classDef startEnd fill:#2d3748,color:#fff,stroke:#1a202c,stroke-width:2px;
    classDef nodeStyle fill:#edf2f7,color:#1a202c,stroke:#cbd5e0,stroke-width:1px;
    
    class START,END startEnd;
    class N1,N2,N3,N4,N5,N6,N7,N8,N9,N10,N11 nodeStyle;
```

---

## 3. 파일 구조

```
.
├── pyproject.toml
├── src/dag_langgraph/
│   ├── __init__.py
│   ├── nodes.py        # 16개 고효용성 노드 카탈로그 (수집 -> 분석 -> 종합 -> 후처리)
│   ├── graph.py        # LangGraph 백엔드 빌더 (StateSchema reducer 기반 병렬 실행 지원)
│   ├── planner.py      # LLM → Plan (다단계 의존성 & 병렬 플랜 생성, stub fallback)
│   ├── executor.py     # Plan → Graph 변환 + run 파사드
│   └── cli.py          # `flow-gen` CLI 엔트리포인트
└── tests/
    ├── test_graph.py
    ├── test_nodes.py
    ├── test_planner.py
    └── test_executor.py
```

---

## 4. Setup

```bash
uv sync --extra dev
cp .env.example .env        # ANTHROPIC_API_KEY (선택, 없으면 stub)
```

---

## 5. Run

```bash
# 애플 기업/주식 분석 DAG 파이프라인 (11개 노드 4단계 파이프라인 생성)
uv run flow-gen "애플 주식 분석 및 최근 뉴스 리포트 작성해줘"

# AI 기술 논문 & 트렌드 DAG 파이프라인
uv run flow-gen "최신 AI 기술 논문 및 트렌드 조사해줘"

# 노드 카탈로그 확인
uv run flow-gen --list-nodes

# Verbose 모드 (단계별 state 변화 확인)
uv run flow-gen -v "종합 리서치 보고서 생성해줘"
```

---

## 6. Test

```bash
uv run pytest
uv run pytest --cov=src --cov-report=term-missing
```

---

## 7. Graph API 직접 사용 (노드 직접 바인딩)

```python
from dag_langgraph import Graph, START, END, NODES

g = Graph()
g.add_node("search_web_news", NODES["search_web_news"].fn)
g.add_node("analyze_news_sentiment", NODES["analyze_news_sentiment"].fn)
g.set_entry_point("search_web_news")
g.add_edge("search_web_news", "analyze_news_sentiment")
g.set_finish_point("analyze_news_sentiment")

state = g.compile().invoke(initial_state={"ticker": "AAPL"})
```

---

## 8. 새 노드 추가

[`src/dag_langgraph/nodes.py`](src/dag_langgraph/nodes.py) 의 `_REGISTRY` 에 `Node(name, description, fn)` 추가.
설명에 **읽는 state 키** + **쓰는 state 키** 명시. Planner 는 이 설명만으로 연결 가능성을 판단한다.

---

## 9. 설계 포인트

| 개념 | 위치 |
|---|---|
| 사전 정의된 16개 노드 | [`nodes.NODES`](src/dag_langgraph/nodes.py) (카탈로그 + 설명) |
| Planner 역할 제한 | 선택 + 엣지 + 병렬 그룹만. 구현/params 불가 |
| Pydantic 스키마 강제 | [`planner.Plan`](src/dag_langgraph/planner.py) |
| Builder API & 병렬 State Reducer | [`graph.Graph`](src/dag_langgraph/graph.py) |
| 사이클 탐지 + 위상정렬 (Kahn) | `graph.Graph._topo_order` |
| 공유 state 데이터 흐름 | `graph.CompiledGraph.invoke` |
| Plan → Graph 변환 | `executor.build` |
| Stub fallback | `planner._stub_plan` |
