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


class Plan(BaseModel):
    thought: str
    initial_state: dict[str, Any] = Field(default_factory=dict)
    selected: list[str]
    edges: list[tuple[str, str]] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    parallel: list[list[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_refs(self) -> Plan:
        selected = set(self.selected)

        for src, dst in self.edges:
            if src not in selected or dst not in selected:
                raise ValueError(f"edge {src}->{dst} 는 selected 외부 노드 참조")

        for step in self.steps:
            unknown = [name for name in step.tasks if name not in selected]
            if unknown:
                raise ValueError(f"step '{step.id}' 에 selected 외부 노드 포함: {unknown}")

        for group in self.parallel:
            if len(group) < 2:
                raise ValueError(f"parallel 그룹은 최소 2개 노드 필요: {group}")
            unknown = [name for name in group if name not in selected]
            if unknown:
                raise ValueError(f"parallel 그룹에 selected 외부 노드 포함: {unknown}")
        return self


class PlanStep(BaseModel):
    id: str
    goal: str
    tasks: list[str] = Field(default_factory=list)


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
    catalog = json.dumps(descriptions(), ensure_ascii=False, indent=2)
    return f"노드 카탈로그:\n{catalog}\n\n목표: {goal}\n\nJSON 계획만 출력."


def plan(goal: str, model: str = "claude-haiku-4-5-20251001") -> Plan:
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
    text = _strip_fences(msg.content[0].text.strip())
    data = json.loads(text)
    return Plan(**data)


def _strip_fences(text: str) -> str:
    if not text.startswith("```"):
        return text
    text = text.split("```", 2)[1]
    if text.startswith("json"):
        text = text[4:]
    return text.strip()


# ---------- 스텁 플랜 ----------

_BASE_ORDER = {
    "order_id": "ORD-2024-001",
    "items": [{"sku": "SHOE-42", "qty": 1, "price": 89000}],
    "payment_method": "card",
    "customer_email": "customer@example.com",
    "shipping_address": {"city": "Seoul", "zip": "04524", "street": "Gangnam-daero 1"},
}


def _stub_plan(goal: str) -> Plan:
    """ANTHROPIC_API_KEY 없을 때 데모용 고정 계획."""
    goal_lower = goal.lower()

    # 할인 쿠폰 주문
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
                ("validate_order", "apply_discount"),
                ("apply_discount", "verify_payment"),
                ("check_inventory", "reserve_inventory"),
                ("verify_payment", "charge_payment"),
                ("reserve_inventory", "create_shipment"),
                ("charge_payment", "create_shipment"),
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
                ["check_inventory", "apply_discount"],
                ["reserve_inventory", "charge_payment"],
                ["send_notification", "update_analytics"],
            ],
        )

    # 재고 확인만
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

    # 기본: 전체 주문 처리 파이프라인
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
            ("validate_order", "verify_payment"),
            ("check_inventory", "reserve_inventory"),
            ("verify_payment", "charge_payment"),
            ("reserve_inventory", "create_shipment"),
            ("charge_payment", "create_shipment"),
            ("create_shipment", "send_notification"),
            ("create_shipment", "update_analytics"),
        ],
        steps=[
            PlanStep(id="step_1", goal="주문 유효성 검사", tasks=["validate_order"]),
            PlanStep(id="step_2", goal="재고 확인 + 결제 검증 병렬", tasks=["check_inventory", "verify_payment"]),
            PlanStep(id="step_3", goal="재고 예약 + 결제 실행 병렬", tasks=["reserve_inventory", "charge_payment"]),
            PlanStep(id="step_4", goal="배송 생성", tasks=["create_shipment"]),
            PlanStep(id="step_5", goal="알림 발송 + 통계 업데이트 병렬", tasks=["send_notification", "update_analytics"]),
        ],
        parallel=[
            ["check_inventory", "verify_payment"],
            ["reserve_inventory", "charge_payment"],
            ["send_notification", "update_analytics"],
        ],
    )
