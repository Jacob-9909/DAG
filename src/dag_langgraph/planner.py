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


SYSTEM = """너는 Flow Planner. 노드는 이미 전부 만들어져 있다.
너의 역할: 주어진 노드 카탈로그에서 필요한 것만 **선택**하고,
그들 사이의 **엣지/단계/병렬 그룹**을 결정한다.
노드 구현, params 는 손대지 마라. 오직 선택 + 연결.

규칙:
- `selected` 에 들어가는 이름은 카탈로그에 존재해야 함
- `edges` 의 양 끝은 selected 에 포함돼야 함
- `steps[*].tasks` 는 selected 이름만 사용
- `parallel[*]` 은 selected 이름만 사용하고, 각 그룹은 길이 2 이상
- 사이클 금지 (DAG)
- 노드가 읽는 state 키는 선행 노드가 쓰거나 `initial_state` 에서 제공돼야 함
- 최소 노드만 선택
- `steps` 는 목적 달성을 위한 멀티태스크 순서
- `parallel` 은 동시에 실행 가능한 노드 그룹(정보성 메타데이터)

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


def _stub_plan(goal: str) -> Plan:
    """ANTHROPIC_API_KEY 없을 때 데모용 고정 계획."""
    # 단순 휴리스틱으로 데모 경로 분기
    goal_lower = goal.lower()
    if "계산" in goal or "calc" in goal_lower:
        return Plan(
            thought=f"stub: '{goal}' → 계산 경로",
            initial_state={"expr": "2 + 3 * 4"},
            selected=["calc"],
            edges=[],
            steps=[
                PlanStep(
                    id="step_1",
                    goal="수식을 계산해 결과를 산출한다",
                    tasks=["calc"],
                )
            ],
            parallel=[],
        )
    if "검색" in goal or "news" in goal_lower:
        return Plan(
            thought=f"stub: '{goal}' → 검색 → 요약 → 한글 번역",
            initial_state={"query": "AI news"},
            selected=["search_web", "summarize_results", "translate_ko"],
            edges=[
                ("search_web", "summarize_results"),
                ("summarize_results", "translate_ko"),
            ],
            steps=[
                PlanStep(
                    id="step_1",
                    goal="검색 결과를 수집한다",
                    tasks=["search_web"],
                ),
                PlanStep(
                    id="step_2",
                    goal="검색 결과를 요약하고 번역한다",
                    tasks=["summarize_results", "translate_ko"],
                ),
            ],
            parallel=[],
        )
    # 기본: 날씨 → 요약 → 영어 번역
    if "fetch_weather" not in NODES:
        raise RuntimeError("NODES 레지스트리에 fetch_weather 누락")
    return Plan(
        thought=f"stub: '{goal}' → 날씨 → 요약 → 영어 번역",
        initial_state={"city": "Seoul"},
        selected=["fetch_weather", "summarize_weather", "translate_en"],
        edges=[
            ("fetch_weather", "summarize_weather"),
            ("summarize_weather", "translate_en"),
        ],
        steps=[
            PlanStep(
                id="step_1",
                goal="도시 날씨를 조회한다",
                tasks=["fetch_weather"],
            ),
            PlanStep(
                id="step_2",
                goal="날씨를 요약하고 영어로 변환한다",
                tasks=["summarize_weather", "translate_en"],
            ),
        ],
        parallel=[],
    )
