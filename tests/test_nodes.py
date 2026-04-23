"""노드 레지스트리 + 개별 노드 동작."""
from __future__ import annotations

import pytest

from dag_langgraph.nodes import NODES, descriptions


@pytest.mark.unit
def test_registry_non_empty_and_unique() -> None:
    names = [d["name"] for d in descriptions()]
    assert len(names) == len(set(names))
    assert "fetch_weather" in NODES
    assert "calc" in NODES


@pytest.mark.unit
def test_fetch_weather_reads_city() -> None:
    out = NODES["fetch_weather"].fn({"city": "Busan"})
    assert out["weather"]["city"] == "Busan"


@pytest.mark.unit
def test_summarize_weather_uses_state() -> None:
    state = {"weather": {"city": "Seoul", "temp_c": 21, "cond": "clear"}}
    out = NODES["summarize_weather"].fn(state)
    assert "Seoul" in out["summary"]


@pytest.mark.unit
def test_translate_chains_summary() -> None:
    state = {"summary": "hello"}
    assert NODES["translate_en"].fn(state)["translated"] == "[en] hello"


@pytest.mark.unit
def test_calc_safe() -> None:
    assert NODES["calc"].fn({"expr": "2 + 3 * 4"})["value"] == 14
    with pytest.raises(ValueError):
        NODES["calc"].fn({"expr": "__import__('os').system('ls')"})
