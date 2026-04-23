"""Planner stub + 카탈로그 검증."""
from __future__ import annotations

import pytest

from flow_gen.nodes import NODES
from flow_gen.planner import Plan, plan


@pytest.mark.unit
def test_stub_plan_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("서울 날씨 알려줘")
    assert isinstance(p, Plan)
    assert all(name in NODES for name in p.selected)


@pytest.mark.unit
def test_stub_plan_calc_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("2+3 계산해줘")
    assert p.selected == ["calc"]


@pytest.mark.unit
def test_stub_plan_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = plan("AI news 검색해줘")
    assert "search_web" in p.selected
