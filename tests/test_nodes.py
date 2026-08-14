"""노드 레지스트리 + 개별 노드 동작 unit 테스트."""
from __future__ import annotations

import pytest

from dag_langgraph.nodes import NODES, descriptions


@pytest.mark.unit
def test_registry_non_empty_and_unique() -> None:
    names = [d["name"] for d in descriptions()]
    assert len(names) == len(set(names))
    assert len(names) >= 15
    assert "search_web_news" in NODES
    assert "fetch_financial_data" in NODES
    assert "generate_full_report" in NODES


@pytest.mark.unit
def test_search_web_news_node() -> None:
    out = NODES["search_web_news"].fn({"ticker": "AAPL"})
    assert "news_articles" in out
    assert len(out["news_articles"]) > 0


@pytest.mark.unit
def test_fetch_financial_data_node() -> None:
    out = NODES["fetch_financial_data"].fn({"ticker": "TSLA"})
    assert out["financial_data"]["ticker"] == "TSLA"
    assert "operating_margin" in out["financial_data"]


@pytest.mark.unit
def test_analyze_news_sentiment_node() -> None:
    articles = [
        {"snippet": "혁신과 높은 성장이 기대된다."},
        {"snippet": "리스크 요인과 마진 압박 존재."}
    ]
    out = NODES["analyze_news_sentiment"].fn({"news_articles": articles})
    assert "news_sentiment" in out
    assert out["news_sentiment"]["label"] in ["Positive", "Negative", "Neutral"]


@pytest.mark.unit
def test_synthesize_swot_node() -> None:
    state = {
        "risks_and_opps": {"risks": ["Risk A"], "opportunities": ["Opp A"]},
        "financial_analysis": {"valuation": "Fair Value"},
        "news_sentiment": {"label": "Positive"}
    }
    out = NODES["synthesize_swot"].fn(state)
    assert "swot_matrix" in out
    assert "Strengths" in out["swot_matrix"]
    assert "Weaknesses" in out["swot_matrix"]


@pytest.mark.unit
def test_generate_full_report_node() -> None:
    state = {
        "topic": "AI Semiconductors",
        "executive_summary": "1. 요약1\n2. 요약2",
        "swot_matrix": {"Strengths": ["S1"], "Weaknesses": ["W1"], "Opportunities": ["O1"], "Threats": ["T1"]},
        "news_sentiment": {"score": 0.5, "label": "Positive"},
        "financial_analysis": {"health_score": 90, "valuation": "Fair"},
        "tech_trends": [{"category": "GPU Architecture", "relevance": "High"}]
    }
    out = NODES["generate_full_report"].fn(state)
    assert "full_report" in out
    assert "# 종합 인텔리전스 보고서: AI Semiconductors" in out["full_report"]
