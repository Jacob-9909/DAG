"""사전 정의된 노드 카탈로그.

각 노드:
- 고정 이름 + 설명 (Planner 프롬프트에 주입됨)
- `fn(state) -> update`: 공유 state dict 에서 읽고 새 키들만 반환
- 인스턴스화/params 지정 없음. Planner 는 이름으로 선택만 한다.
"""
from __future__ import annotations

import ast
import operator as op
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

State = dict[str, Any]


@dataclass(frozen=True)
class Node:
    name: str
    description: str
    fn: Callable[[State], State]


# ---------- 내부 구현 ----------

_BINOPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Mod: op.mod, ast.Pow: op.pow, ast.FloorDiv: op.floordiv,
}
_UNOPS = {ast.UAdd: op.pos, ast.USub: op.neg}


def _safe_eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
        return _UNOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"허용되지 않은 표현식: {type(node).__name__}")


# ---------- 노드 함수 ----------

def _fetch_weather(state: State) -> State:
    city = state.get("city", "Seoul")
    return {"weather": {"city": city, "temp_c": 21, "cond": "clear"}}


def _search_web(state: State) -> State:
    query = state.get("query", "")
    return {"results": [f"fake hit for '{query}'"]}


def _summarize_weather(state: State) -> State:
    w = state["weather"]
    text = f"{w['city']} 날씨: {w['cond']}, 기온 {w['temp_c']}도"
    return {"summary": text[:120]}


def _summarize_results(state: State) -> State:
    items = state.get("results", [])
    return {"summary": "; ".join(str(x) for x in items)[:120]}


def _translate_en(state: State) -> State:
    return {"translated": f"[en] {state['summary']}"}


def _translate_ko(state: State) -> State:
    return {"translated": f"[ko] {state['summary']}"}


def _calc(state: State) -> State:
    tree = ast.parse(state["expr"], mode="eval")
    return {"value": _safe_eval(tree)}


# ---------- 레지스트리 ----------

_REGISTRY: list[Node] = [
    Node(
        name="fetch_weather",
        description="state['city'] 기반 날씨 조회. writes: weather={city,temp_c,cond}",
        fn=_fetch_weather,
    ),
    Node(
        name="search_web",
        description="state['query'] 로 웹 검색. writes: results[list]",
        fn=_search_web,
    ),
    Node(
        name="summarize_weather",
        description="state['weather'] 를 한국어 요약. writes: summary",
        fn=_summarize_weather,
    ),
    Node(
        name="summarize_results",
        description="state['results'] 를 연결 요약. writes: summary",
        fn=_summarize_results,
    ),
    Node(
        name="translate_en",
        description="state['summary'] 를 영어로 번역. writes: translated",
        fn=_translate_en,
    ),
    Node(
        name="translate_ko",
        description="state['summary'] 를 한국어로 번역. writes: translated",
        fn=_translate_ko,
    ),
    Node(
        name="calc",
        description="state['expr'] 산술 계산(+-*/%**//). writes: value",
        fn=_calc,
    ),
]

NODES: dict[str, Node] = {n.name: n for n in _REGISTRY}


def descriptions() -> list[dict[str, str]]:
    """Planner 프롬프트용 카탈로그."""
    return [{"name": n.name, "description": n.description} for n in _REGISTRY]
