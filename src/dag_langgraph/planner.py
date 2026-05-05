"""Planner. LLM 은 기존 노드에서 선택 + 엣지 + 단계 정보를 결정.

출력 스키마:
    {
      "thought": "...",
      "initial_state": {...},           # 노드 실행 전 주입할 값
      "selected": ["node_a", "node_b"], # 레지스트리의 이름만
      "edges": [["node_a", "node_b"]],  # 선택된 노드 간 방향성 엣지
      "steps": [                         # 목표 달성을 위한 멀티태스크 단계
        {"id": "step_1", "goal": "...", "tasks": ["node_a"]}
      ],
      "parallel": [["node_a", "node_b"]] # 병렬 실행 가능한 노드 그룹
    }
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field, model_validator

from dag_langgraph.nodes import NODES, descriptions

logger = logging.getLogger(__name__)


# ---------- Plan 스키마 ----------

class Plan(BaseModel):
    """LLM이 반환하는 계획. Pydantic이 타입·참조 무결성을 자동 검증한다."""
    thought: str                              # LLM의 추론 과정 (디버깅용)
    initial_state: dict[str, Any] = Field(default_factory=dict)  # 그래프 실행 시 초기 state
    selected: list[str]                       # 사용할 노드 이름 목록
    edges: list[tuple[str, str]] = Field(default_factory=list)   # (출발 노드, 도착 노드) 쌍
    steps: list[PlanStep] = Field(default_factory=list)          # 실행 단계 설명 (정보성)
    parallel: list[list[str]] = Field(default_factory=list)      # 병렬 실행 가능한 노드 그룹

    @model_validator(mode="after")
    def _validate_refs(self) -> Plan:
        """selected에 없는 노드를 edges/steps/parallel이 참조하면 즉시 오류."""
        selected = set(self.selected)

        # 엣지 양쪽 끝이 모두 selected 안에 있어야 한다
        for src, dst in self.edges:
            if src not in selected or dst not in selected:
                raise ValueError(f"edge {src}->{dst} 는 selected 외부 노드 참조")

        # 각 step의 task도 selected 안에 있어야 한다
        for step in self.steps:
            unknown = [name for name in step.tasks if name not in selected]
            if unknown:
                raise ValueError(f"step '{step.id}' 에 selected 외부 노드 포함: {unknown}")

        # parallel 그룹은 최소 2개, 모두 selected 안에 있어야 한다
        for group in self.parallel:
            if len(group) < 2:
                raise ValueError(f"parallel 그룹은 최소 2개 노드 필요: {group}")
            unknown = [name for name in group if name not in selected]
            if unknown:
                raise ValueError(f"parallel 그룹에 selected 외부 노드 포함: {unknown}")
        return self


class PlanStep(BaseModel):
    """실행 단계 하나. 사람이 읽기 좋은 정보이며, 실제 그래프 실행에는 사용되지 않는다."""
    id: str
    goal: str
    tasks: list[str] = Field(default_factory=list)


# ---------- LLM 시스템 프롬프트 ----------
# Planner의 역할과 제약을 명확히 지시한다.
# 노드 구현을 수정하거나 새 노드를 만드는 것은 Planner의 역할이 아님을 강조.

SYSTEM = """너는 주문 처리 Flow Planner. 노드는 이미 전부 만들어져 있다.
너의 역할: 주어진 노드 카탈로그에서 필요한 것만 **선택**하고,
그들 사이의 **엣지/단계/병렬 그룹**을 결정한다.

규칙:
- `selected` 에 들어가는 이름은 카탈로그에 존재해야 함
- `edges` 의 양 끝은 selected 에 포함돼야 함
- `steps[*].tasks` 는 selected 이름만 사용
- `parallel[*]` 은 selected 이름만 사용하고, 각 그룹은 길이 2 이상
- 사이클 금지 (DAG)
- 노드가 읽는 state 키는 선행 노드가 쓰거나 `initial_state` 에서 제공돼야 함
- 최소 노드만 선택
- check_inventory 와 verify_payment 는 서로 의존하지 않으므로 병렬 가능
- send_notification 과 update_analytics 는 서로 의존하지 않으므로 병렬 가능

출력: JSON only. 스키마:
{
  "thought": "...",
  "initial_state": {...},
  "selected": ["..."],
  "edges": [["src","dst"]],
  "steps": [{"id":"step_1","goal":"...","tasks":["node_a"]}],
  "parallel": [["node_a","node_b"]]
}
"""


def _prompt(goal: str) -> str:
    """노드 카탈로그 + 목표를 합쳐 LLM에게 전달할 유저 메시지를 만든다."""
    catalog = json.dumps(descriptions(), ensure_ascii=False, indent=2)
    return f"노드 카탈로그:\n{catalog}\n\n목표: {goal}\n\nJSON 계획만 출력."


def plan(goal: str, model: str = "claude-haiku-4-5-20251001") -> Plan:
    """목표(자연어)를 받아 Plan을 반환한다.

    ANTHROPIC_API_KEY가 없으면 stub plan으로 폴백해 API 없이도 동작한다.
    """
    # API 키가 없으면 실제 LLM 호출 없이 미리 만들어둔 stub plan 반환
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.info("ANTHROPIC_API_KEY 없음 → stub plan")
        return _stub_plan(goal)
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic 미설치 → stub plan")
        return _stub_plan(goal)

    client = Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM,
        messages=[{"role": "user", "content": _prompt(goal)}],
    )
    # LLM 응답에서 ```json ... ``` 코드 펜스를 제거하고 파싱
    text = _strip_fences(msg.content[0].text.strip())
    data = json.loads(text)
    return Plan(**data)


def _strip_fences(text: str) -> str:
    """LLM이 응답을 ```json ... ``` 형식으로 감싸는 경우 펜스를 제거한다."""
    if not text.startswith("```"):
        return text
    text = text.split("```", 2)[1]
    if text.startswith("json"):
        text = text[4:]
    return text.strip()


# ---------- 스텁 플랜 ----------
# API 키 없이도 세 가지 시나리오를 테스트할 수 있도록 미리 만들어둔 고정 계획.
# 실제 서비스에서는 이 부분이 LLM 응답으로 대체된다.

# 모든 스텁 플랜이 공통으로 사용하는 기본 주문 데이터
_BASE_ORDER = {
    "order_id": "ORD-2024-001",
    "items": [{"sku": "SHOE-42", "qty": 1, "price": 89000}],
    "payment_method": "card",
    "customer_email": "customer@example.com",
    "shipping_address": {"city": "Seoul", "zip": "04524", "street": "Gangnam-daero 1"},
}


def _stub_plan(goal: str) -> Plan:
    """ANTHROPIC_API_KEY 없을 때 데모용 고정 계획. 목표 키워드로 경로를 분기한다."""
    goal_lower = goal.lower()

    # 시나리오 1: 할인 쿠폰 → apply_discount 노드가 추가로 삽입됨
    if "할인" in goal or "쿠폰" in goal or "discount" in goal_lower:
        return Plan(
            thought="할인 쿠폰 적용 → 검증·재고·결제 병렬 → 배송 → 알림·통계 병렬",
            initial_state={**_BASE_ORDER, "coupon_code": "SAVE20"},
            selected=[
                "validate_order",
                "check_inventory",
                "apply_discount",
                "verify_payment",
                "reserve_inventory",
                "charge_payment",
                "create_shipment",
                "send_notification",
                "update_analytics",
            ],
            edges=[
                ("validate_order", "check_inventory"),
                ("validate_order", "apply_discount"),   # 할인 계산은 재고 확인과 병렬
                ("apply_discount", "verify_payment"),   # 할인 후 결제 검증
                ("check_inventory", "reserve_inventory"),
                ("verify_payment", "charge_payment"),
                ("reserve_inventory", "create_shipment"),
                ("charge_payment", "create_shipment"),  # fan-in: 둘 다 완료 후 배송
                ("create_shipment", "send_notification"),
                ("create_shipment", "update_analytics"),
            ],
            steps=[
                PlanStep(id="step_1", goal="주문 유효성 검사", tasks=["validate_order"]),
                PlanStep(id="step_2", goal="재고 확인 + 할인 계산 병렬", tasks=["check_inventory", "apply_discount"]),
                PlanStep(id="step_3", goal="재고 예약 + 결제 실행 병렬", tasks=["reserve_inventory", "verify_payment", "charge_payment"]),
                PlanStep(id="step_4", goal="배송 생성", tasks=["create_shipment"]),
                PlanStep(id="step_5", goal="알림 발송 + 통계 업데이트 병렬", tasks=["send_notification", "update_analytics"]),
            ],
            parallel=[
                ["check_inventory", "apply_discount"],    # 재고 확인·할인 계산 동시에
                ["reserve_inventory", "charge_payment"],  # 예약·결제 동시에
                ["send_notification", "update_analytics"],
            ],
        )

    # 시나리오 2: 재고 확인만 → 최소 2개 노드로 구성된 단순 파이프라인
    if "재고" in goal or "inventory" in goal_lower:
        return Plan(
            thought="주문 검증 후 재고만 확인",
            initial_state=_BASE_ORDER,
            selected=["validate_order", "check_inventory"],
            edges=[("validate_order", "check_inventory")],
            steps=[
                PlanStep(id="step_1", goal="주문 유효성 검사", tasks=["validate_order"]),
                PlanStep(id="step_2", goal="재고 확인", tasks=["check_inventory"]),
            ],
            parallel=[],
        )

    # 시나리오 3 (기본): 전체 주문 처리 파이프라인
    #   validate_order
    #     ├── check_inventory ──→ reserve_inventory ─┐
    #     └── verify_payment ──→ charge_payment ──────┤
    #                                                  ↓
    #                                          create_shipment
    #                                            ├── send_notification
    #                                            └── update_analytics
    return Plan(
        thought="전체 주문 처리: 검증 → 재고·결제 병렬 → 배송 → 알림·통계 병렬",
        initial_state=_BASE_ORDER,
        selected=[
            "validate_order",
            "check_inventory",
            "verify_payment",
            "reserve_inventory",
            "charge_payment",
            "create_shipment",
            "send_notification",
            "update_analytics",
        ],
        edges=[
            ("validate_order", "check_inventory"),
            ("validate_order", "verify_payment"),         # 재고 확인·결제 검증 병렬 시작
            ("check_inventory", "reserve_inventory"),
            ("verify_payment", "charge_payment"),
            ("reserve_inventory", "create_shipment"),
            ("charge_payment", "create_shipment"),        # fan-in: 둘 다 완료 후 배송
            ("create_shipment", "send_notification"),
            ("create_shipment", "update_analytics"),      # 알림·통계 병렬 시작
        ],
        steps=[
            PlanStep(id="step_1", goal="주문 유효성 검사", tasks=["validate_order"]),
            PlanStep(id="step_2", goal="재고 확인 + 결제 검증 병렬", tasks=["check_inventory", "verify_payment"]),
            PlanStep(id="step_3", goal="재고 예약 + 결제 실행 병렬", tasks=["reserve_inventory", "charge_payment"]),
            PlanStep(id="step_4", goal="배송 생성", tasks=["create_shipment"]),
            PlanStep(id="step_5", goal="알림 발송 + 통계 업데이트 병렬", tasks=["send_notification", "update_analytics"]),
        ],
        parallel=[
            ["check_inventory", "verify_payment"],        # 서로 의존 없음 → 동시 실행
            ["reserve_inventory", "charge_payment"],      # 서로 의존 없음 → 동시 실행
            ["send_notification", "update_analytics"],    # 서로 의존 없음 → 동시 실행
        ],
    )
