"""Planner. LLM 은 기존 노드에서 선택 + 엣지만 결정.

출력 스키마:
    {
      "thought": "...",
      "initial_state": {...},           # 노드 실행 전 주입할 값
      "selected": ["node_a", "node_b"], # 레지스트리의 이름만
      "edges": [["node_a", "node_b"]]   # 선택된 노드 간 방향성 엣지
    }
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from flow_gen.nodes import NODES, descriptions

logger = logging.getLogger(__name__)


class Plan(BaseModel):
    thought: str
    initial_state: dict[str, Any] = Field(default_factory=dict)
    selected: list[str]
    edges: list[tuple[str, str]] = Field(default_factory=list)


SYSTEM = """너는 Flow Planner. 노드는 이미 전부 만들어져 있다.
너의 역할: 주어진 노드 카탈로그에서 필요한 것만 **선택**하고, 그들 사이의 **엣지**를 결정한다.
노드 구현, params 는 손대지 마라. 오직 선택 + 연결.

규칙:
- `selected` 에 들어가는 이름은 카탈로그에 존재해야 함
- `edges` 의 양 끝은 selected 에 포함돼야 함
- 사이클 금지 (DAG)
- 노드가 읽는 state 키는 선행 노드가 쓰거나 `initial_state` 에서 제공돼야 함
- 최소 노드만 선택

출력: JSON only. 스키마:
{"thought": "...", "initial_state": {...}, "selected": ["..."], "edges": [["src","dst"]]}
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
        )
    # 기본: 날씨 → 요약 → 영어 번역
    assert "fetch_weather" in NODES  # sanity
    return Plan(
        thought=f"stub: '{goal}' → 날씨 → 요약 → 영어 번역",
        initial_state={"city": "Seoul"},
        selected=["fetch_weather", "summarize_weather", "translate_en"],
        edges=[
            ("fetch_weather", "summarize_weather"),
            ("summarize_weather", "translate_en"),
        ],
    )
