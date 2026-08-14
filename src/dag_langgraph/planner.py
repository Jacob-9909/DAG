"""Planner. LLM은 기존 노드 카탈로그에서 필요한 노드를 선택하고, 엣지 및 다단계 병렬 execution 플랜을 결정.

출력 스키마:
    {
      "thought": "...",
      "initial_state": {...},           # 노드 실행 전 주입할 값
      "selected": ["node_a", "node_b"], # 레지스트리의 노드 이름 목록
      "edges": [["node_a", "node_b"]],  # 선택된 노드 간 방향성 엣지 (의존 관계)
      "steps": [                         # 목표 달성을 위한 멀티태스크 단계
        {"id": "step_1", "goal": "...", "tasks": ["node_a"]}
      ],
      "parallel": [["node_a", "node_b"]] # 동시 실행 가능한 병렬 노드 그룹
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


class PlanStep(BaseModel):
    id: str
    goal: str
    tasks: list[str] = Field(default_factory=list)


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


SYSTEM = """너는 전문적인 Intelligence Flow Planner이다. 노드는 카탈로그에 사전 정의되어 있다.
너의 역할: 유저의 목표를 분석하여 카탈로그에서 필요한 노드를 **선택(selected)**하고,
각 노드가 읽고 쓰는 `state` 키 의존성에 맞춰 **방향성 엣지(edges)**, **단계(steps)**, 및 **병렬 실행 가능한 그룹(parallel)**을 작성한다.

규칙:
1. `selected`: 카탈로그에 존재하는 노드 이름만 포함. 데이터 수집 -> 분석 -> 종합 -> 후처리 단계별로 풍부하게 선택할 것.
2. `edges`: (src, dst) 형태. dst 노드가 읽는 state 키를 src 노드가 미리 쓴(write) 구조여야 함.
3. `parallel`: 입력을 공유하고 동시에 실행 가능한 노드들의 그룹 (길이 2 이상).
4. 사이클 금지 (반드시 유향 비순환 그래프 DAG 생성).
5. initial_state: 그래프 실행 시 처음에 필요한 데이터 (예: topic, ticker, query 등)를 사전 세팅.

출력 형식: 오직 JSON만 출력할 것.
{
  "thought": "단계별 의존성 및 병렬 구성 이유",
  "initial_state": {"ticker": "AAPL", "topic": "AI Market"},
  "selected": ["search_web_news", "fetch_financial_data", "analyze_news_sentiment", "calculate_financial_ratios", "generate_full_report"],
  "edges": [
    ["search_web_news", "analyze_news_sentiment"],
    ["fetch_financial_data", "calculate_financial_ratios"],
    ["analyze_news_sentiment", "generate_full_report"],
    ["calculate_financial_ratios", "generate_full_report"]
  ],
  "steps": [
    {"id": "step_1", "goal": "멀티소스 데이터 수집", "tasks": ["search_web_news", "fetch_financial_data"]},
    {"id": "step_2", "goal": "데이터 분석", "tasks": ["analyze_news_sentiment", "calculate_financial_ratios"]},
    {"id": "step_3", "goal": "보고서 작성", "tasks": ["generate_full_report"]}
  ],
  "parallel": [
    ["search_web_news", "fetch_financial_data"],
    ["analyze_news_sentiment", "calculate_financial_ratios"]
  ]
}
"""


def _prompt(goal: str) -> str:
    catalog = json.dumps(descriptions(), ensure_ascii=False, indent=2)
    return f"노드 카탈로그:\n{catalog}\n\n목표: {goal}\n\n위 목표를 성취하기 위한 완벽한 DAG JSON 플랜을 작성하라."


def plan(goal: str, model: str = "claude-haiku-4-5-20251001") -> Plan:
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.info("ANTHROPIC_API_KEY 없음 → 풍부한 실용적 DAG stub plan 실행")
        return _stub_plan(goal)
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic 미설치 → stub plan 실행")
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
    """ANTHROPIC_API_KEY 없을 때 데모용 다단계 풍부한 DAG 플랜."""
    goal_lower = goal.lower()

    # 1. 기업/주식/재무 분석 대규모 DAG 파이프라인 (11개 노드)
    if any(k in goal_lower for k in ["기업", "주식", "재무", "aapl", "stock", "financial"]):
        selected = [
            "search_web_news", "fetch_financial_data", "fetch_community_sentiment", # 수집
            "analyze_news_sentiment", "calculate_financial_ratios", "extract_risks_and_opportunities", # 분석
            "synthesize_swot", "generate_executive_summary", "generate_full_report", # 종합
            "extract_action_items", "translate_report_ko" # 후처리
        ]
        edges = [
            # 수집 -> 분석
            ("search_web_news", "analyze_news_sentiment"),
            ("search_web_news", "extract_risks_and_opportunities"),
            ("fetch_financial_data", "calculate_financial_ratios"),
            ("fetch_financial_data", "extract_risks_and_opportunities"),
            
            # 분석 -> 종합
            ("analyze_news_sentiment", "synthesize_swot"),
            ("calculate_financial_ratios", "synthesize_swot"),
            ("extract_risks_and_opportunities", "synthesize_swot"),
            ("analyze_news_sentiment", "generate_executive_summary"),
            ("calculate_financial_ratios", "generate_executive_summary"),
            ("synthesize_swot", "generate_full_report"),
            ("generate_executive_summary", "generate_full_report"),
            
            # 종합 -> 후처리
            ("synthesize_swot", "extract_action_items"),
            ("generate_full_report", "translate_report_ko")
        ]
        return Plan(
            thought=f"'{goal}' 요청에 대해 수집->분석->SWOT합성->종합보고서->액션아이템/번역으로 이어지는 11개 노드 DAG 구성",
            initial_state={"ticker": "AAPL", "query": "Apple Market Position"},
            selected=selected,
            edges=edges,
            steps=[
                PlanStep(id="step_1", goal="멀티소스 병렬 수집 (뉴스, 재무, 커뮤니티)", tasks=["search_web_news", "fetch_financial_data", "fetch_community_sentiment"]),
                PlanStep(id="step_2", goal="독립 심층 분석 (감성, 재무비율, 리스크/기회)", tasks=["analyze_news_sentiment", "calculate_financial_ratios", "extract_risks_and_opportunities"]),
                PlanStep(id="step_3", goal="SWOT 및 경영진 요약/종합 보고서 생성", tasks=["synthesize_swot", "generate_executive_summary", "generate_full_report"]),
                PlanStep(id="step_4", goal="후처리 (Action Item 추출 & 한국어 번역)", tasks=["extract_action_items", "translate_report_ko"])
            ],
            parallel=[
                ["search_web_news", "fetch_financial_data", "fetch_community_sentiment"],
                ["analyze_news_sentiment", "calculate_financial_ratios", "extract_risks_and_opportunities"],
                ["synthesize_swot", "generate_executive_summary"],
                ["extract_action_items", "translate_report_ko"]
            ]
        )

    # 2. 기술/논문/트렌드 파이프라인 (9개 노드)
    if any(k in goal_lower for k in ["기술", "논문", "트렌드", "ai", "tech", "paper"]):
        selected = [
            "fetch_tech_papers", "search_web_news",
            "cluster_tech_trends", "extract_key_entities", "analyze_news_sentiment",
            "generate_executive_summary", "generate_full_report",
            "translate_report_en", "generate_social_posts"
        ]
        edges = [
            ("fetch_tech_papers", "cluster_tech_trends"),
            ("fetch_tech_papers", "extract_key_entities"),
            ("search_web_news", "extract_key_entities"),
            ("search_web_news", "analyze_news_sentiment"),
            ("analyze_news_sentiment", "generate_executive_summary"),
            ("cluster_tech_trends", "generate_full_report"),
            ("generate_executive_summary", "generate_full_report"),
            ("generate_executive_summary", "translate_report_en"),
            ("generate_executive_summary", "generate_social_posts")
        ]
        return Plan(
            thought=f"'{goal}' 요청에 맞춰 학술 논문 및 시장 뉴스 수집 -> 기술 트렌드/엔티티 분석 -> 마케팅 포스트 및 번역 생성 DAG 구성",
            initial_state={"topic": "AI DAG Engine", "query": "LLM Orchestration Trends"},
            selected=selected,
            edges=edges,
            steps=[
                PlanStep(id="step_1", goal="기술 논문 및 시장 뉴스 병렬 수집", tasks=["fetch_tech_papers", "search_web_news"]),
                PlanStep(id="step_2", goal="기술 트렌드 클러스터링 및 엔티티 추출", tasks=["cluster_tech_trends", "extract_key_entities", "analyze_news_sentiment"]),
                PlanStep(id="step_3", goal="종합 기술보고서 작성", tasks=["generate_executive_summary", "generate_full_report"]),
                PlanStep(id="step_4", goal="소셜 미디어 발행글 및 영문 번역 생성", tasks=["translate_report_en", "generate_social_posts"])
            ],
            parallel=[
                ["fetch_tech_papers", "search_web_news"],
                ["cluster_tech_trends", "extract_key_entities", "analyze_news_sentiment"],
                ["translate_report_en", "generate_social_posts"]
            ]
        )

    # 3. 기본 종합 AI 리서치 인텔리전스 대형 파이프라인 (10개 노드)
    selected = [
        "search_web_news", "fetch_tech_papers", "fetch_community_sentiment",
        "analyze_news_sentiment", "extract_key_entities", "extract_risks_and_opportunities",
        "synthesize_swot", "generate_executive_summary", "generate_full_report",
        "extract_action_items"
    ]
    edges = [
        ("search_web_news", "analyze_news_sentiment"),
        ("search_web_news", "extract_key_entities"),
        ("search_web_news", "extract_risks_and_opportunities"),
        ("fetch_tech_papers", "extract_key_entities"),
        ("analyze_news_sentiment", "synthesize_swot"),
        ("extract_risks_and_opportunities", "synthesize_swot"),
        ("analyze_news_sentiment", "generate_executive_summary"),
        ("synthesize_swot", "generate_full_report"),
        ("generate_executive_summary", "generate_full_report"),
        ("synthesize_swot", "extract_action_items")
    ]
    return Plan(
        thought=f"'{goal}'에 대해 멀티소스 데이터 수집->분석->SWOT합성->보고서->액션아이템 생성을 수행하는 10개 노드 DAG 구성",
        initial_state={"topic": goal, "query": goal},
        selected=selected,
        edges=edges,
        steps=[
            PlanStep(id="step_1", goal="멀티소스 3종 데이터 병렬 수집", tasks=["search_web_news", "fetch_tech_papers", "fetch_community_sentiment"]),
            PlanStep(id="step_2", goal="다각도 분석 (감성, 엔티티, 리스크/기회)", tasks=["analyze_news_sentiment", "extract_key_entities", "extract_risks_and_opportunities"]),
            PlanStep(id="step_3", goal="SWOT 매트릭스 및 경영진 요약 생성", tasks=["synthesize_swot", "generate_executive_summary"]),
            PlanStep(id="step_4", goal="종합 마크다운 보고서 및 Action Item 추출", tasks=["generate_full_report", "extract_action_items"])
        ],
        parallel=[
            ["search_web_news", "fetch_tech_papers", "fetch_community_sentiment"],
            ["analyze_news_sentiment", "extract_key_entities", "extract_risks_and_opportunities"],
            ["generate_full_report", "extract_action_items"]
        ]
    )
