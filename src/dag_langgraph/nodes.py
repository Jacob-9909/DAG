"""실용적이고 독립 가치가 높은 다단계 AI 리서치 및 인텔리전스 노드 카탈로그.

각 노드는:
- 명확한 이름과 상세한 프롬프트용 설명 (reads / writes 명시)
- 독립적으로 실행 시에도 실질적인 가치를 제공하는 고유 로직
- 공유 state dict를 입력받아 새로운 지식/분석 키를 생성하여 반환 (fn(state) -> update)
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

State = dict[str, Any]


@dataclass(frozen=True)
class Node:
    name: str
    description: str
    fn: Callable[[State], State]


# =====================================================================
# 1. 데이터 수집 / 정보 입수 노드 (Data Ingestion & Gathering)
# =====================================================================

def _search_web_news(state: State) -> State:
    """주제/기업 관련 최신 뉴스 수집 및 주요 헤드라인 구성."""
    query = state.get("query") or state.get("topic") or state.get("ticker", "General Market")
    # 실제 수집 로직 모사 / 확장 가능한 구조
    articles = [
        {"title": f"{query} 관련 최신 시장 동향 분석", "source": "TechDaily", "snippet": f"{query} 분야의 수요 증가 및 기술 혁신 가속화."},
        {"title": f"{query} 주요 규제 및 리스크 요인 발생", "source": "FinancialNews", "snippet": f"공급망 문제 및 글로벌 금리 변동이 {query} 시장에 영향."},
        {"title": f"{query} 신규 차세대 솔루션 출시 소식", "source": "BizWire", "snippet": f"새로운 파트너십 발표로 {query}의 점유율 확대 기대."}
    ]
    return {"news_articles": articles}


def _fetch_financial_data(state: State) -> State:
    """기업 티커 기반 재무 지표(매출, 영업이익, PER, PBR 등) 수집."""
    ticker = state.get("ticker", "AAPL")
    financials = {
        "ticker": ticker,
        "revenue_yoy": 14.5,
        "operating_margin": 28.2,
        "per": 24.5,
        "pbr": 8.1,
        "debt_to_equity": 45.0,
        "cash_flow_status": "Positive",
    }
    return {"financial_data": financials}


def _fetch_tech_papers(state: State) -> State:
    """주제 관련 최신 학술/기술 논문 메타데이터 수집."""
    topic = state.get("topic") or state.get("query", "AI Technology")
    papers = [
        {"title": f"Scalable Architectures for {topic}", "year": 2025, "citations": 142, "abstract": f"Novel approaches to optimize performance in {topic} domains."},
        {"title": f"Safety and Robustness in {topic}", "year": 2025, "citations": 89, "abstract": f"Empirical study on fault tolerance and risk mitigation for {topic}."}
    ]
    return {"tech_papers": papers}


def _fetch_community_sentiment(state: State) -> State:
    """SNS 및 커뮤니티 트렌드/멘션 반응 데이터 수집."""
    topic = state.get("topic") or state.get("query") or state.get("ticker", "Product")
    community_data = {
        "mention_volume": "High",
        "trend_direction": "Rising (+32%)",
        "top_keywords": [topic, "혁신", "성능", "가격", "기대감"],
        "user_ratings_avg": 4.3,
    }
    return {"community_posts": community_data}


# =====================================================================
# 2. 분석 & 인텔리전스 노드 (Analysis & Processing)
# =====================================================================

def _analyze_news_sentiment(state: State) -> State:
    """수집된 뉴스 아티클들의 긍정/부정/중립 감성 및 감성 점수 연산."""
    articles = state.get("news_articles", [])
    if not articles:
        return {"news_sentiment": {"score": 0.0, "label": "Neutral", "positive_ratio": 0.5}}
    
    # 텍스트 스키밍 기반 감성 분석 로직
    pos_count = sum(1 for a in articles if any(w in a.get("snippet", "") for w in ["증가", "혁신", "기대", "확대"]))
    neg_count = sum(1 for a in articles if any(w in a.get("snippet", "") for w in ["리스크", "규제", "문제", "변동"]))
    total = len(articles)
    
    pos_ratio = pos_count / total if total > 0 else 0.5
    score = round((pos_count - neg_count) / total, 2) if total > 0 else 0.0
    label = "Positive" if score > 0.1 else ("Negative" if score < -0.1 else "Neutral")
    
    return {
        "news_sentiment": {
            "score": score,
            "label": label,
            "positive_ratio": round(pos_ratio, 2),
            "analyzed_count": total
        }
    }


def _extract_key_entities(state: State) -> State:
    """뉴스 및 기술 문서에서 주요 인물, 기업, 핵심 기술 키워드 추출."""
    articles = state.get("news_articles", [])
    papers = state.get("tech_papers", [])
    
    entities = {
        "key_technologies": ["DAG Engine", "LLM Orchestration", "Async Processing"],
        "mentioned_companies": ["OpenAI", "Anthropic", "Google", "Apple"],
        "key_terms": [a.get("title", "").split()[0] for a in articles if a.get("title")]
    }
    return {"entities": entities}


def _extract_risks_and_opportunities(state: State) -> State:
    """뉴스 및 재무/커뮤니티 데이터를 기반으로 리스크(Risk) 및 기회(Opportunity) 요인 분리 추출."""
    articles = state.get("news_articles", [])
    financials = state.get("financial_data", {})
    
    risks = ["거시 경제 불확실성 및 금리 영향", "경쟁 심화로 인한 마진 압박"]
    opportunities = ["차세대 기술 도입을 통한 효율성 제고", "신규 글로벌 시장 진출 기회"]
    
    if financials.get("operating_margin", 0) > 20:
        opportunities.append("높은 영업이익율 기반의 우수한 재무적 유연성")
    if financials.get("debt_to_equity", 0) > 100:
        risks.append("부채 비율 증가로 인한 재무 리스크")
        
    return {"risks_and_opps": {"risks": risks, "opportunities": opportunities}}


def _calculate_financial_ratios(state: State) -> State:
    """재무 데이터 기반 종합 재무건전성 및 밸류에이션 점수 연산."""
    fin = state.get("financial_data", {})
    per = fin.get("per", 20)
    rev_growth = fin.get("revenue_yoy", 10)
    
    health_score = 85 if fin.get("cash_flow_status") == "Positive" else 60
    valuation_status = "Undervalued" if per < 15 else ("Overvalued" if per > 35 else "Fair Value")
    
    return {
        "financial_analysis": {
            "health_score": health_score,
            "valuation": valuation_status,
            "growth_rate_yoy": f"{rev_growth}%",
            "summary_comment": f"성장률 {rev_growth}% 및 PER {per} 수준으로 {valuation_status} 상태 평가됨."
        }
    }


def _cluster_tech_trends(state: State) -> State:
    """기술 논문 데이터를 도메인별 트렌드 카테고리로 클러스터링."""
    papers = state.get("tech_papers", [])
    trends = [
        {"category": "Orchestration & Workflow", "relevance": "High", "paper_count": len(papers)},
        {"category": "Fault Tolerance & Safety", "relevance": "Medium", "paper_count": 1}
    ]
    return {"tech_trends": trends}


# =====================================================================
# 3. 종합 & 요약 노드 (Synthesis & Summarization)
# =====================================================================

def _synthesize_swot(state: State) -> State:
    """리스크/기회 요인 및 재무/뉴스 분석 결과를 통합하여 SWOT 매트릭스 작성."""
    r_and_o = state.get("risks_and_opps", {})
    fin_eval = state.get("financial_analysis", {})
    sent = state.get("news_sentiment", {})
    
    swot = {
        "Strengths": [f"긍정적 시장 감성 ({sent.get('label', 'Neutral')})", "견고한 기술력 및 브랜드"],
        "Weaknesses": [f"재무 평가: {fin_eval.get('valuation', 'Fair Value')}"],
        "Opportunities": r_and_o.get("opportunities", []),
        "Threats": r_and_o.get("risks", [])
    }
    return {"swot_matrix": swot}


def _generate_executive_summary(state: State) -> State:
    """경영진 및 의사결정권자를 위한 3줄 핵심 요약 생성."""
    topic = state.get("topic") or state.get("query") or state.get("ticker", "Subject")
    sent = state.get("news_sentiment", {}).get("label", "Neutral")
    fin = state.get("financial_analysis", {}).get("valuation", "N/A")
    
    bullets = [
        f"1. [{topic}] 관련 시장 감성은 전반적으로 '{sent}' 상태를 보이고 있음.",
        f"2. 재무 및 밸류에이션 관점에서 '{fin}' 수준으로 평가되며 성장성 보유.",
        f"3. 주요 기회 요인과 차세대 기술 트렌드를 결합한 전략적 대응이 요구됨."
    ]
    return {"executive_summary": "\n".join(bullets)}


def _generate_full_report(state: State) -> State:
    """모든 수집 및 분석 데이터를 종합한 최종 마크다운 인텔리전스 보고서 작성."""
    topic = state.get("topic") or state.get("query") or state.get("ticker", "Report Goal")
    exec_sum = state.get("executive_summary", "요약 정보 없음")
    swot = state.get("swot_matrix", {})
    sent = state.get("news_sentiment", {})
    fin = state.get("financial_analysis", {})
    trends = state.get("tech_trends", [])
    
    report_md = f"""# 종합 인텔리전스 보고서: {topic}

## 1. Executive Summary
{exec_sum}

## 2. 시장 감성 & 재무 분석
- **시장 감성 점수**: {sent.get('score', 0.0)} ({sent.get('label', 'Neutral')})
- **재무 건전성 점수**: {fin.get('health_score', 'N/A')}/100
- **밸류에이션**: {fin.get('valuation', 'N/A')}

## 3. SWOT 분석
- **Strengths**: {', '.join(swot.get('Strengths', []))}
- **Weaknesses**: {', '.join(swot.get('Weaknesses', []))}
- **Opportunities**: {', '.join(swot.get('Opportunities', []))}
- **Threats**: {', '.join(swot.get('Threats', []))}

## 4. 기술 트렌드 카테고리
"""
    for t in trends:
        report_md += f"- **{t['category']}** (관련성: {t['relevance']})\n"
        
    return {"full_report": report_md}


# =====================================================================
# 4. 후처리 & 액션 가공 노드 (Post-Processing & Publishing)
# =====================================================================

def _extract_action_items(state: State) -> State:
    """종합 보고서 및 SWOT 분석을 기반으로 실천 가능한 Action Item 체크리스트 생성."""
    swot = state.get("swot_matrix", {})
    threats = swot.get("Threats", [])
    opps = swot.get("Opportunities", [])
    
    actions = [
        f"[우선순위 높음] {opps[0] if opps else '신규 기회 선점을 위한 모니터링 강화'}",
        f"[리스크 관리] {threats[0] if threats else '주요 리스크 요소에 대한 헤징 방안 마련'}",
        "[시행 과제] 분기별 실적 및 뉴스 감성 추이 모니터링 체계 구축"
    ]
    return {"action_items": actions}


def _translate_report_ko(state: State) -> State:
    """생성된 보고서나 요약을 한국어로 번역/정제."""
    report = state.get("full_report") or state.get("executive_summary", "")
    return {"translated_report_ko": f"[한국어 정제 버전]\n{report}"}


def _translate_report_en(state: State) -> State:
    """생성된 보고서나 요약을 영어로 번역."""
    exec_sum = state.get("executive_summary", "")
    en_text = f"[English Version]\nExecutive Summary:\n" + exec_sum.replace("관련 시장 감성은", "Market sentiment is").replace("상태를 보이고 있음", "status.")
    return {"translated_report_en": en_text}


def _generate_social_posts(state: State) -> State:
    """Executive Summary 및 주요 인사이트 기반 소셜 미디어(LinkedIn / X) 포스트 생성."""
    topic = state.get("topic") or state.get("query") or state.get("ticker", "Trends")
    exec_sum = state.get("executive_summary", "")
    
    linkedin_post = f"🚀 [{topic} 시장 동향 & 종합 인텔리전스]\n\n{exec_sum}\n\n#BusinessIntelligence #Analytics #{topic.replace(' ', '')}"
    x_post = f"📊 [{topic}] 핵심 3줄 요약:\n{exec_sum[:100]}...\n#Trends"
    
    return {"social_posts": {"linkedin": linkedin_post, "x_twitter": x_post}}


# =====================================================================
# 레지스트리 정의 (총 16개 노드)
# =====================================================================

_REGISTRY: list[Node] = [
    # 수집
    Node(
        name="search_web_news",
        description="reads: topic/query/ticker. 주제 관련 최신 뉴스 3건 수집. writes: news_articles",
        fn=_search_web_news,
    ),
    Node(
        name="fetch_financial_data",
        description="reads: ticker. 기업 재무 지표(매출성장률, 영업이익률, PER 등) 수집. writes: financial_data",
        fn=_fetch_financial_data,
    ),
    Node(
        name="fetch_tech_papers",
        description="reads: topic/query. 학술/기술 논문 데이터 수집. writes: tech_papers",
        fn=_fetch_tech_papers,
    ),
    Node(
        name="fetch_community_sentiment",
        description="reads: topic/query/ticker. SNS 및 커뮤니티 멘션/트렌드 수집. writes: community_posts",
        fn=_fetch_community_sentiment,
    ),
    
    # 분석
    Node(
        name="analyze_news_sentiment",
        description="reads: news_articles. 뉴스 아티클 감성 분석(점수, Label, 긍정비율). writes: news_sentiment",
        fn=_analyze_news_sentiment,
    ),
    Node(
        name="extract_key_entities",
        description="reads: news_articles, tech_papers. 주요 기업, 인물, 핵심 기술 키워드 추출. writes: entities",
        fn=_extract_key_entities,
    ),
    Node(
        name="extract_risks_and_opportunities",
        description="reads: news_articles, financial_data. 리스크 요인 및 기회 요인 추출. writes: risks_and_opps",
        fn=_extract_risks_and_opportunities,
    ),
    Node(
        name="calculate_financial_ratios",
        description="reads: financial_data. 재무 비율 및 건전성/밸류에이션 연산. writes: financial_analysis",
        fn=_calculate_financial_ratios,
    ),
    Node(
        name="cluster_tech_trends",
        description="reads: tech_papers. 기술 논문 기반 기술 트렌드 카테고리화. writes: tech_trends",
        fn=_cluster_tech_trends,
    ),
    
    # 종합
    Node(
        name="synthesize_swot",
        description="reads: risks_and_opps, financial_analysis, news_sentiment. SWOT 매트릭스 작성. writes: swot_matrix",
        fn=_synthesize_swot,
    ),
    Node(
        name="generate_executive_summary",
        description="reads: news_sentiment, financial_analysis, topic/ticker. 3줄 핵심 요약 작성. writes: executive_summary",
        fn=_generate_executive_summary,
    ),
    Node(
        name="generate_full_report",
        description="reads: executive_summary, swot_matrix, news_sentiment, financial_analysis, tech_trends. 종합 마크다운 보고서 작성. writes: full_report",
        fn=_generate_full_report,
    ),
    
    # 후처리
    Node(
        name="extract_action_items",
        description="reads: swot_matrix, full_report. 실행 가능한 우선순위 Action Items 추출. writes: action_items",
        fn=_extract_action_items,
    ),
    Node(
        name="translate_report_ko",
        description="reads: full_report / executive_summary. 보고서를 한국어로 정제/번역. writes: translated_report_ko",
        fn=_translate_report_ko,
    ),
    Node(
        name="translate_report_en",
        description="reads: executive_summary / full_report. 요약/보고서를 영어로 번역. writes: translated_report_en",
        fn=_translate_report_en,
    ),
    Node(
        name="generate_social_posts",
        description="reads: executive_summary. LinkedIn 및 X/Twitter 소셜 미디어 포스트 생성. writes: social_posts",
        fn=_generate_social_posts,
    ),
]

NODES: dict[str, Node] = {n.name: n for n in _REGISTRY}


def descriptions() -> list[dict[str, str]]:
    """Planner 프롬프트용 카탈로그."""
    return [{"name": n.name, "description": n.description} for n in _REGISTRY]
