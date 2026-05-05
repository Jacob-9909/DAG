# dag-langgraph

동적 DAG 오케스트레이터. 노드는 미리 정의하고, 엣지는 LLM Planner가 목표에 따라 즉석에서 결정한다.

## 아키텍처

```
유저 목표 (자연어)
  ↓
Planner (LLM) — 노드 카탈로그를 보고 필요한 노드 선택 + 엣지 결정
  ↓ Plan JSON
  { selected: [...], edges: [[src, dst], ...], initial_state: {...} }
  ↓
executor.build(plan) — Plan을 LangGraph StateGraph로 조립
  ↓
compile() → invoke(initial_state) → 최종 state dict
```

**핵심 원칙:** `nodes.py`의 노드 함수들은 서로의 존재를 모른다. 어떤 노드 다음에 무엇이 실행될지는 코드에 없고, 쿼리가 들어올 때마다 LLM이 JSON으로 결정한다.

## 노드 구조 (주문 처리 파이프라인)

DAG의 의존성·병렬성·합류(fan-in)가 모두 드러나는 도메인으로 설계됐다.

```
validate_order                    ← 항상 첫 번째 (필수 필드 검증)
    ├── check_inventory    ┐      ← 서로 무관 → 병렬 실행 가능
    └── verify_payment     ┘
          │
    reserve_inventory             ← check_inventory 결과 필요
    charge_payment                ← verify_payment 결과 필요
          │
    create_shipment               ← 둘 다 완료돼야 실행 (fan-in)
          │
    ├── send_notification  ┐      ← 서로 무관 → 병렬 실행 가능
    └── update_analytics   ┘

선택적:
    apply_discount    — coupon_code 있을 때 verify_payment 앞에 삽입
    validate_address  — 해외 배송 등 주소 검증 필요 시 create_shipment 앞에 삽입
```

| DAG 개념 | 예시 |
|---------|------|
| 순차 의존 | `check_inventory` → `reserve_inventory` (재고 없으면 예약 불가) |
| 병렬 실행 | `check_inventory` ↔ `verify_payment` (서로 무관) |
| fan-in (합류) | `reserve_inventory` + `charge_payment` → `create_shipment` |
| 선택적 경로 | 쿠폰 있을 때만 `apply_discount` 삽입 |

## 파일 구조

```
src/dag_langgraph/
├── nodes.py      노드 카탈로그 — Node(name, description, fn) 등록. 엣지 정보 없음
├── planner.py    LLM → Plan(selected, edges, initial_state). API 키 없으면 stub
├── executor.py   Plan → Graph 변환 + run 파사드
├── graph.py      LangGraph StateGraph 래퍼 (병렬 merge reducer, 사이클 탐지)
└── cli.py        flow-gen CLI 진입점

tests/
├── test_nodes.py      노드 함수 단위 테스트 + 전체 happy-path 수동 실행
├── test_planner.py    stub Plan 검증
├── test_executor.py   Plan → 그래프 변환·실행·엣지 검증
└── test_graph.py      Graph 빌더 단위 테스트
```

## 설치 및 실행

```bash
uv sync --extra dev
cp .env.example .env   # ANTHROPIC_API_KEY 입력 (없으면 stub plan 사용)
```

```bash
# 전체 주문 처리
uv run flow-gen "주문 처리해줘"

# 할인 쿠폰 경로 (apply_discount 노드 추가)
uv run flow-gen "할인 쿠폰 적용해서 주문 처리"

# 재고 확인만 (2노드 단순 파이프라인)
uv run flow-gen "재고 확인만 해줘"

# 노드 카탈로그 출력
uv run flow-gen --list-nodes

# 단계별 로그
uv run flow-gen -v "주문 처리해줘"
```

## 테스트

```bash
uv run --extra dev pytest
uv run --extra dev pytest --cov=src --cov-report=term-missing
```

## 새 노드 추가

`src/dag_langgraph/nodes.py`의 `_REGISTRY`에 추가한다.

```python
Node(
    name="send_sms",
    description=(
        "고객 휴대폰 SMS 발송. "
        "writes: sms_sent. "
        "requires: create_shipment. send_notification 과 병렬 실행 가능."
    ),
    fn=_send_sms,
)
```

description에 **읽는 state 키**와 **쓰는 state 키**를 명시하면 Planner가 연결 가능성을 스스로 판단한다.

## 직접 그래프 조립 (API)

```python
from dag_langgraph import Graph, START, END, NODES

g = Graph()
g.add_node("validate_order", NODES["validate_order"].fn)
g.add_node("check_inventory", NODES["check_inventory"].fn)
g.add_edge(START, "validate_order")
g.add_edge("validate_order", "check_inventory")
g.add_edge("check_inventory", END)

state = g.compile().invoke(initial_state={
    "order_id": "ORD-001",
    "items": [{"sku": "ITEM-A", "qty": 1, "price": 10000}],
    "payment_method": "card",
    "customer_email": "user@example.com",
})
```

## 설계 포인트

| 항목 | 위치 |
|------|------|
| 노드 카탈로그 (엣지 없음) | `nodes.NODES` |
| Planner 역할 제한 | 선택 + 엣지만. 구현·params 불가 |
| Pydantic 스키마 강제 | `planner.Plan` |
| 병렬 fan-in 지원 | `graph.py` — `Annotated[dict, merge_reducer]` |
| 사이클 탐지 (Kahn) | `graph.Graph._topo_order` |
| START/END 자동 연결 | `executor.build` — 루트·리프 자동 감지 |
| Stub fallback | `planner._stub_plan` — API 키 없어도 동작 |
