"""
IRONAGE AI Analytics System v5.0
주간/월간 트렌드 분석 모듈

변경 사항 (v4.4):
- 이슈 연속성 추적 (IssueTracker DB 연동)
- 표준화 갭 누적 저장 (StandardizationGap DB 연동)
- 보고서에 "연속 이슈 알림" 섹션 자동 추가

변경 사항 (v4.3):
- 개조식(ㅇ) 포맷 전면 적용
- 핵심이슈/트렌드/기술하이라이트 하단에 관련 뉴스 제목(링크) 포함
- 기술 하이라이트 주간/월간 모두 추가
- 2단계 AI 분석: GPT-4o 초안 → Claude 검증/보완 → 최종본
- 인사이트 항목 신규 추가
- 향후 전망 항목 강화
"""

import json
import datetime
import re
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict

from news_engine import (
    log_info, log_warning, log_error,
    get_db_session, NewsArticle, IssueTracker, StandardizationGap,
    OPENAI_API_KEY,
    performance_monitor,
    get_openai_client,
    get_claude_client,
    OPENAI_MODEL_DEFAULT,
    CLAUDE_MODEL_DEFAULT,
)

# ==============================================================================
# --- 통계 데이터 생성 ---
# ==============================================================================

@performance_monitor
def generate_statistics_data(articles: List[Dict], period_days: int) -> Dict:
    """주간/월간 통계 데이터 생성"""
    log_info(f"📊 {period_days}일간 통계 데이터 생성 중...")

    total_articles = len(articles)

    daily_counts = defaultdict(int)
    for article in articles:
        date_str = article.get('published', article.get('collected_at', ''))
        if date_str:
            try:
                if isinstance(date_str, str):
                    date_obj = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    date_obj = date_str
                daily_counts[date_obj.strftime('%Y-%m-%d')] += 1
            except Exception as e:
                log_error(f"일별 날짜 파싱 오류: {e}")

    source_counts = Counter([article.get('source', 'Unknown') for article in articles])

    keywords = []
    for article in articles:
        title = article.get('title', '')
        words = [w for w in title.split() if len(w) >= 2 and any('가' <= c <= '힣' for c in w)]
        keywords.extend(words)

    keyword_counts = Counter(keywords).most_common(30)

    quality_scores = [article.get('quality_score', 0) for article in articles if article.get('quality_score')]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

    daily_trend = [{'date': d, 'count': c} for d, c in sorted(daily_counts.items())]
    source_chart_data = [{'source': s, 'count': c} for s, c in source_counts.most_common(8)]
    keyword_cloud_data = [{'word': w, 'frequency': f} for w, f in keyword_counts[:30]]

    hour_distribution = defaultdict(int)
    for article in articles:
        date_str = article.get('published', article.get('collected_at', ''))
        if date_str:
            try:
                if isinstance(date_str, str):
                    date_obj = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    date_obj = date_str
                hour_distribution[date_obj.hour] += 1
            except Exception as e:
                log_error(f"시간대 날짜 파싱 오류: {e}")

    statistics = {
        'total_articles': total_articles,
        'period_days': period_days,
        'daily_counts': dict(sorted(daily_counts.items())),
        'source_distribution': dict(source_counts.most_common(10)),
        'top_keywords': keyword_counts,
        'avg_quality_score': round(avg_quality, 2),
        'analyzed_articles': len([a for a in articles if a.get('is_analyzed')]),
        'chart_data': {
            'daily_trend': daily_trend,
            'source_distribution': source_chart_data,
            'keyword_cloud': keyword_cloud_data,
            'hour_distribution': dict(sorted(hour_distribution.items()))
        }
    }

    log_info("  ✅ 통계 생성 완료")
    return statistics


# ==============================================================================
# --- 2단계 AI 분석 공통 헬퍼 ---
# ==============================================================================

def _build_title_link_map(articles: List[Dict]) -> Dict[str, str]:
    """기사 제목 → URL 매핑 딕셔너리 생성"""
    return {
        article.get('title', ''): article.get('link', '')
        for article in articles
        if article.get('title')
    }


def _run_dual_ai_analysis(
    initial_prompt: str,
    validation_prompt_builder,
    initial_system: str,
    validation_system: str,
    max_tokens_initial: int = 2500,
    max_tokens_validation: int = 2500,
) -> Dict:
    """
    2단계 AI 분석:
      1단계: GPT-4o로 초안 분석
      2단계: Claude로 검증/보완 후 최종본 반환

    validation_prompt_builder(initial_result: Dict) -> str
    """
    # ── 1단계: GPT-4o 초안 ──────────────────────────────────────────────────
    log_info("  [1단계] GPT-4o 초안 분석 중...")
    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model=OPENAI_MODEL_DEFAULT,
            messages=[
                {"role": "system", "content": initial_system},
                {"role": "user", "content": initial_prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens_initial,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-z]*\n?', '', text).rstrip('`').strip()
        initial_result = json.loads(text)
        log_info("  ✅ GPT-4o 초안 완료")
    except Exception as e:
        log_error(f"❌ GPT-4o 초안 분석 실패: {e}")
        return {}

    # ── 2단계: Claude 검증/보완 ──────────────────────────────────────────────
    log_info("  [2단계] Claude 검증/보완 중...")
    try:
        val_prompt = validation_prompt_builder(initial_result)
        claude = get_claude_client()
        msg = claude.messages.create(
            model=CLAUDE_MODEL_DEFAULT,
            max_tokens=max_tokens_validation,
            system=validation_system,
            messages=[{"role": "user", "content": val_prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-z]*\n?', '', text).rstrip('`').strip()
        final_result = json.loads(text)
        log_info("  ✅ Claude 검증/보완 완료")
        final_result['_analysis_chain'] = 'GPT-4o 초안 → Claude 검증/보완'
        return final_result
    except Exception as e:
        log_warning(f"⚠️ Claude 검증 실패 ({e}), GPT-4o 초안으로 대체합니다.")
        initial_result['_analysis_chain'] = 'GPT-4o 단독 (Claude 검증 불가)'
        return initial_result


# ==============================================================================
# --- 주간 트렌드 AI 분석 ---
# ==============================================================================

@performance_monitor
def analyze_weekly_trends(articles: List[Dict]) -> Dict:
    """주간 트렌드 2단계 AI 분석 (GPT-4o → Claude)"""
    log_info("🔍 주간 트렌드 AI 분석 시작...")

    if not articles:
        log_warning("⚠️ 분석할 뉴스가 없습니다.")
        return {'summary': '분석할 데이터가 없습니다.', 'key_issues': [], 'trends': []}

    stats = generate_statistics_data(articles, period_days=7)
    title_link_map = _build_title_link_map(articles)

    news_summaries = []
    for i, article in enumerate(articles[:50], 1):
        summary = f"{i}. [{article.get('source', 'Unknown')}] {article.get('title', '')}"
        if article.get('analysis_result'):
            summary += f"\n   분석: {article['analysis_result'][:200]}"
        news_summaries.append(summary)

    news_text = "\n\n".join(news_summaries)

    initial_prompt = f"""
당신은 TTA(한국정보통신기술협회) 수석 전략 컨설턴트입니다.
아래 주간 ICT 뉴스를 분석하여 보직자용 전략 인사이트 보고서 초안을 JSON으로 작성하십시오.

[분석 기간] 최근 7일  |  [기사 수] {stats['total_articles']}개
[주요 키워드] {', '.join([kw[0] for kw in stats['top_keywords'][:10]])}

[뉴스 목록]
{news_text}

아래 JSON 스키마를 정확히 따르십시오:
{{
  "executive_summary": "ㅇ 핵심 전략 메시지 1\\nㅇ 핵심 전략 메시지 2\\nㅇ 핵심 전략 메시지 3",
  "key_issues": [
    {{
      "title": "이슈 제목",
      "description": ["ㅇ 현황 설명", "ㅇ 주요 플레이어 동향", "ㅇ 기술적 특이사항"],
      "impact_level": "상/중/하",
      "standardization_gap": "표준화 공백 또는 선점 필요 영역",
      "tta_action_item": "TTA 구체적 대응 방향",
      "related_articles": ["뉴스 목록의 기사 제목 그대로 복사 1", "기사 제목 2"]
    }}
  ],
  "trends": [
    {{
      "trend": "트렌드 제목",
      "description": ["ㅇ 트렌드 설명", "ㅇ 표준화 영향"],
      "related_articles": ["기사 제목 1", "기사 제목 2"]
    }}
  ],
  "technology_highlights": [
    {{
      "technology": "기술명",
      "description": ["ㅇ 기술 현황", "ㅇ 국내외 동향"],
      "related_articles": ["기사 제목 1"]
    }}
  ],
  "insights": ["ㅇ 핵심 인사이트 1", "ㅇ 핵심 인사이트 2", "ㅇ 핵심 인사이트 3"],
  "outlook": ["ㅇ 차주 예상 동향 1", "ㅇ 모니터링 리스크 1", "ㅇ 대응 권고 1"]
}}

규칙:
- 모든 서술은 "ㅇ"로 시작하는 개조식으로 작성
- related_articles는 반드시 위 뉴스 목록에 실제로 존재하는 제목만 기재 (최대 3개)
- impact_level '상' 이슈를 앞에 배치, 최대 5개
- technology_highlights 최대 4개
"""

    def build_validation_prompt(initial: Dict) -> str:
        return f"""
당신은 ICT 표준화 전략 전문가입니다.
아래는 GPT-4o가 생성한 주간 ICT 트렌드 보고서 초안입니다.
내용의 정확성, 완결성, 개조식 표현의 일관성을 검토하고 최종본을 동일한 JSON 스키마로 반환하십시오.

[검토 기준]
1. 모든 설명은 "ㅇ"로 시작하는 개조식인지 확인
2. related_articles가 실제 기사 제목과 일치하는지 검토
3. insights와 outlook이 구체적이고 실행 가능한지 보완
4. technology_highlights가 누락된 핵심 기술은 없는지 확인
5. 중복 내용 제거, 논리적 일관성 확보

[GPT-4o 초안]
{json.dumps(initial, ensure_ascii=False, indent=2)}

동일한 JSON 스키마로 최종본만 반환하십시오.
"""

    initial_system = "당신은 ICT/통신 업계 전문 애널리스트입니다. JSON 형식으로만 응답하세요."
    validation_system = "당신은 ICT 표준화 전략 전문가입니다. 검증 후 JSON 형식으로만 응답하세요."

    analysis_result = _run_dual_ai_analysis(
        initial_prompt=initial_prompt,
        validation_prompt_builder=build_validation_prompt,
        initial_system=initial_system,
        validation_system=validation_system,
        max_tokens_initial=2500,
        max_tokens_validation=2500,
    )

    if not analysis_result:
        return {
            'executive_summary': '트렌드 분석 중 오류가 발생했습니다.',
            'key_issues': [], 'trends': [], 'technology_highlights': [],
            'insights': [], 'outlook': [], 'statistics': stats
        }

    analysis_result['statistics'] = stats
    analysis_result['title_link_map'] = title_link_map

    # 이슈 연속성 추적 + 표준화 갭 저장
    recurring = track_issue_continuity(
        analysis_result.get('key_issues', []), title_link_map, report_type='weekly'
    )
    save_standardization_gaps(analysis_result.get('key_issues', []), report_type='weekly')
    analysis_result['recurring_issues'] = recurring

    log_info(f"  ✅ 분석 완료: {len(analysis_result.get('key_issues', []))}개 핵심 이슈")
    return analysis_result


# ==============================================================================
# --- 월간 트렌드 AI 분석 ---
# ==============================================================================

@performance_monitor
def analyze_monthly_trends(articles: List[Dict]) -> Dict:
    """월간 트렌드 2단계 AI 분석 (GPT-4o → Claude)"""
    log_info("🔍 월간 트렌드 AI 분석 시작...")

    if not articles:
        log_warning("⚠️ 분석할 뉴스가 없습니다.")
        return {'summary': '분석할 데이터가 없습니다.', 'key_issues': [], 'trends': []}

    stats = generate_statistics_data(articles, period_days=30)
    title_link_map = _build_title_link_map(articles)

    articles_by_week = defaultdict(list)
    for article in articles:
        date_str = article.get('published', article.get('collected_at', ''))
        if date_str:
            try:
                if isinstance(date_str, str):
                    date_obj = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    date_obj = date_str
                if date_obj.tzinfo is not None:
                    date_obj = date_obj.replace(tzinfo=None)
                week_num = (datetime.datetime.now() - date_obj).days // 7
                if week_num < 4:
                    articles_by_week[week_num].append(article)
            except Exception as e:
                log_error(f"월간 주차 날짜 파싱 오류: {e}")

    weekly_summaries = []
    for week in range(4):
        week_articles = articles_by_week.get(week, [])
        if week_articles:
            top_titles = [a['title'] for a in week_articles[:3]]
            weekly_summaries.append(
                f"Week {week+1}: {len(week_articles)}개 기사 | {', '.join(top_titles)}"
            )

    sampled = articles[:100] if len(articles) > 100 else articles
    news_summaries = [
        f"{i}. [{a.get('source', 'Unknown')}] {a.get('title', '')}"
        for i, a in enumerate(sampled, 1)
    ]

    news_text = "\n".join(news_summaries)
    weekly_text = "\n".join(weekly_summaries)

    initial_prompt = f"""
당신은 TTA(한국정보통신기술협회) 수석 전략 컨설턴트입니다.
아래 월간 ICT 뉴스를 분석하여 보직자용 월간 전략 인사이트 보고서 초안을 JSON으로 작성하십시오.

[분석 기간] 최근 30일  |  [기사 수] {stats['total_articles']}개
[주요 키워드] {', '.join([kw[0] for kw in stats['top_keywords'][:15]])}
[주차별 동향] {weekly_text}

[대표 뉴스 (상위 100건)]
{news_text[:8000]}

아래 JSON 스키마를 정확히 따르십시오:
{{
  "executive_summary": "ㅇ 월간 핵심 전략 메시지 1\\nㅇ 핵심 전략 메시지 2\\nㅇ 핵심 전략 메시지 3\\nㅇ 핵심 전략 메시지 4",
  "key_issues": [
    {{
      "title": "핵심 이슈 제목",
      "description": ["ㅇ 현황 분석", "ㅇ 주요 플레이어 동향", "ㅇ 인과관계 분석"],
      "impact_level": "상/중/하",
      "weekly_evolution": "ㅇ 한 달간 이슈 전개 추이",
      "tta_strategic_direction": "ㅇ TTA 중장기 대응 방향",
      "related_articles": ["기사 제목 1", "기사 제목 2", "기사 제목 3"]
    }}
  ],
  "trends": [
    {{
      "trend": "트렌드 제목",
      "description": ["ㅇ 트렌드 설명", "ㅇ ICT 생태계 영향"],
      "prediction": ["ㅇ 익월 전망", "ㅇ 분기별 시장 전망"],
      "related_articles": ["기사 제목 1", "기사 제목 2"]
    }}
  ],
  "technology_highlights": [
    {{
      "technology": "기술명",
      "description": ["ㅇ 기술 현황", "ㅇ 국내외 동향", "ㅇ 표준화 기회"],
      "related_articles": ["기사 제목 1", "기사 제목 2"]
    }}
  ],
  "standardization_focus": [
    {{
      "area": "집중 표준화 영역",
      "reason": ["ㅇ 이유 1", "ㅇ 이유 2"]
    }}
  ],
  "insights": ["ㅇ 핵심 인사이트 1", "ㅇ 핵심 인사이트 2", "ㅇ 핵심 인사이트 3", "ㅇ 핵심 인사이트 4"],
  "market_insights": ["ㅇ 시장 거시 지표 분석 1", "ㅇ 경쟁 구도 변화 1"],
  "outlook": ["ㅇ 익월 핵심 모니터링 포인트 1", "ㅇ 전략 수립 시 고려 사항 1", "ㅇ 대응 권고 1"]
}}

규칙:
- 모든 서술은 "ㅇ"로 시작하는 개조식
- related_articles는 위 뉴스 목록에 실제로 존재하는 제목만 (최대 3개)
- impact_level '상' 이슈 우선 배치, 최대 7개
- technology_highlights 최대 5개
"""

    def build_validation_prompt(initial: Dict) -> str:
        return f"""
당신은 ICT 표준화 전략 전문가입니다.
아래는 GPT-4o가 생성한 월간 ICT 트렌드 보고서 초안입니다.
내용의 정확성, 완결성, 개조식 표현의 일관성을 검토하고 최종본을 동일한 JSON 스키마로 반환하십시오.

[검토 기준]
1. 모든 설명이 "ㅇ"로 시작하는 개조식인지 확인 및 수정
2. related_articles가 실제 기사 제목과 일치하는지 검토
3. insights/outlook이 구체적이고 실행 가능한지 보완
4. technology_highlights에 누락된 핵심 기술 보완
5. standardization_focus 영역이 현실적이고 타당한지 검토
6. market_insights와 insights가 중복되지 않도록 조정

[GPT-4o 초안]
{json.dumps(initial, ensure_ascii=False, indent=2)}

동일한 JSON 스키마로 최종본만 반환하십시오.
"""

    initial_system = "당신은 ICT/통신 업계 시니어 애널리스트입니다. JSON 형식으로만 응답하세요."
    validation_system = "당신은 ICT 표준화 전략 전문가입니다. 검증 후 JSON 형식으로만 응답하세요."

    analysis_result = _run_dual_ai_analysis(
        initial_prompt=initial_prompt,
        validation_prompt_builder=build_validation_prompt,
        initial_system=initial_system,
        validation_system=validation_system,
        max_tokens_initial=3000,
        max_tokens_validation=3000,
    )

    if not analysis_result:
        return {
            'executive_summary': '트렌드 분석 중 오류가 발생했습니다.',
            'key_issues': [], 'trends': [], 'technology_highlights': [],
            'insights': [], 'market_insights': [], 'outlook': [],
            'statistics': stats
        }

    analysis_result['statistics'] = stats
    analysis_result['title_link_map'] = title_link_map

    # 이슈 연속성 추적 + 표준화 갭 저장
    recurring = track_issue_continuity(
        analysis_result.get('key_issues', []), title_link_map, report_type='monthly'
    )
    save_standardization_gaps(analysis_result.get('key_issues', []), report_type='monthly')
    analysis_result['recurring_issues'] = recurring

    log_info(f"  ✅ 분석 완료: {len(analysis_result.get('key_issues', []))}개 핵심 이슈")
    return analysis_result


# ==============================================================================
# --- 공통 유틸 ---
# ==============================================================================

def _resolve_article_links(titles: List[str], title_link_map: Dict[str, str]) -> List[Dict]:
    """
    AI가 반환한 기사 제목 목록을 {title, link} 형태로 변환.
    정확 매칭 우선, 부분 매칭 fallback.
    """
    result = []
    for title in titles:
        link = title_link_map.get(title, '')
        if not link:
            # 부분 매칭
            for stored_title, stored_link in title_link_map.items():
                if title[:20] in stored_title or stored_title[:20] in title:
                    link = stored_link
                    break
        result.append({'title': title, 'link': link})
    return result


def _bullet_lines(value) -> List[str]:
    """
    문자열 또는 리스트를 개조식 라인 목록으로 정규화.
    이미 "ㅇ"로 시작하면 그대로, 아니면 앞에 "ㅇ " 붙임.
    """
    if isinstance(value, str):
        lines = [v.strip() for v in value.split('\n') if v.strip()]
    elif isinstance(value, list):
        lines = [str(v).strip() for v in value if str(v).strip()]
    else:
        return []
    return [l if l.startswith('ㅇ') else f'ㅇ {l}' for l in lines]


# ==============================================================================
# --- 구글 문서 생성 ---
# ==============================================================================

@performance_monitor
def generate_trend_report_doc(analysis_result: Dict, report_type: str = 'weekly') -> Tuple[str, str]:
    """트렌드 분석 결과를 구글 문서로 생성 (개조식 포맷)"""
    from news_engine import get_google_docs_service

    period_name = "주간" if report_type == 'weekly' else "월간"
    today = datetime.datetime.now().strftime('%Y년 %m월 %d일')
    report_title = f"[TTA] {period_name} ICT 트렌드 분석 리포트 ({today})"

    log_info(f"📝 구글 문서 생성 중: {report_title}")

    try:
        from news_engine import REPORT_FOLDER_ID
        docs_service, drive_service = get_google_docs_service()
        # 공유 드라이브 폴더에 직접 생성
        _f = drive_service.files().create(
            body={
                'name': report_title,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [REPORT_FOLDER_ID],
            },
            supportsAllDrives=True,
            fields='id',
        ).execute()
        doc_id = _f['id']
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

        title_link_map = analysis_result.get('title_link_map', {})
        stats = analysis_result.get('statistics', {})
        chain = analysis_result.get('_analysis_chain', 'AI 자동 분석')

        # ── 문서 내용 블록 구성 (역순 삽입이므로 아래서부터 쌓임) ─────────────
        blocks = []

        def add(text: str):
            blocks.append({'insertText': {'location': {'index': 1}, 'text': text}})

        # 푸터
        add(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀\n"
            f"분석 체계: {chain}\n"
            "본 보고서는 IRONAGE AI Analytics System으로 자동 생성되었습니다.\n"
        )

        # 향후 전망
        outlook = _bullet_lines(analysis_result.get('outlook', []))
        if outlook:
            add("🔮 향후 전망\n\n" + "\n".join(outlook) + "\n\n")

        # 인사이트
        insights = _bullet_lines(analysis_result.get('insights', []))
        if insights:
            add("💡 인사이트\n\n" + "\n".join(insights) + "\n\n")

        # 월간 전용 섹션
        if report_type == 'monthly':
            # 표준화 집중 영역
            sf_list = analysis_result.get('standardization_focus', [])
            if sf_list:
                sf_text = "📐 표준화 집중 영역\n\n"
                for sf in sf_list:
                    sf_text += f"■ {sf.get('area', '')}\n"
                    for line in _bullet_lines(sf.get('reason', [])):
                        sf_text += f"  {line}\n"
                    sf_text += "\n"
                add(sf_text)

            # 시장 인사이트
            market = _bullet_lines(analysis_result.get('market_insights', []))
            if market:
                add("💼 시장 인사이트\n\n" + "\n".join(market) + "\n\n")

        # 트렌드 분석
        trends = analysis_result.get('trends', [])
        if trends:
            trend_text = "📍 트렌드 분석\n\n"
            for i, trend in enumerate(trends, 1):
                trend_text += f"{i}. {trend.get('trend', '')}\n"
                for line in _bullet_lines(trend.get('description', [])):
                    trend_text += f"   {line}\n"
                for line in _bullet_lines(trend.get('prediction', [])):
                    trend_text += f"   {line}\n"
                related = _resolve_article_links(trend.get('related_articles', []), title_link_map)
                if related:
                    trend_text += "   [관련 뉴스]\n"
                    for art in related:
                        link_str = f" ({art['link']})" if art['link'] else ""
                        trend_text += f"   - {art['title']}{link_str}\n"
                trend_text += "\n"
            add(trend_text)

        # 연속 이슈 알림 섹션
        recurring = analysis_result.get('recurring_issues', [])
        if recurring:
            rec_text = "⚠️ 연속 등장 이슈 (주의 필요)\n\n"
            for r in recurring:
                arrow = {'상승': '📈', '유지': '➡️', '하락': '📉', '신규': '🆕'}.get(
                    r.get('trend_direction', ''), '•')
                rec_text += (
                    f"  • {r['title']} "
                    f"[{r['occurrence_count']}회 연속 / 중요도: {r['impact_level']} / "
                    f"추세: {arrow}{r.get('trend_direction','')} / "
                    f"최초: {r.get('first_seen','')}]\n"
                )
            rec_text += "\n"
            add(rec_text)

        # 핵심 이슈
        issues = analysis_result.get('key_issues', [])
        if issues:
            issue_text = "🔥 핵심 이슈\n\n"
            for i, issue in enumerate(issues, 1):
                level = issue.get('impact_level', issue.get('importance', '하'))
                level_mark = "🔴" if level == '상' else "🟡" if level == '중' else "🟢"
                issue_text += f"{i}. {level_mark} {issue.get('title', '')} [영향도: {level}]\n"
                for line in _bullet_lines(issue.get('description', [])):
                    issue_text += f"   {line}\n"
                if issue.get('standardization_gap'):
                    issue_text += f"   ㅇ [표준화 공백] {issue['standardization_gap']}\n"
                if issue.get('tta_action_item'):
                    issue_text += f"   ㅇ [TTA 대응] {issue['tta_action_item']}\n"
                if issue.get('weekly_evolution'):
                    issue_text += f"   ㅇ [이슈 추이] {issue['weekly_evolution']}\n"
                if issue.get('tta_strategic_direction'):
                    issue_text += f"   ㅇ [전략 방향] {issue['tta_strategic_direction']}\n"
                related = _resolve_article_links(issue.get('related_articles', []), title_link_map)
                if related:
                    issue_text += "   [관련 뉴스]\n"
                    for art in related:
                        link_str = f" ({art['link']})" if art['link'] else ""
                        issue_text += f"   - {art['title']}{link_str}\n"
                issue_text += "\n"
            add(issue_text)

        # 통계
        stats_text = (
            "📈 주요 통계\n\n"
            f"ㅇ 전체 기사 수: {stats.get('total_articles', 0)}개\n"
            f"ㅇ 분석 완료: {stats.get('analyzed_articles', 0)}개\n"
            f"ㅇ 평균 품질 점수: {stats.get('avg_quality_score', 0)}\n"
            f"ㅇ 주요 출처: {', '.join(list(stats.get('source_distribution', {}).keys())[:5])}\n\n"
        )
        add(stats_text)

        # Executive Summary
        summary_lines = _bullet_lines(analysis_result.get('executive_summary', ''))
        summary_text = "📊 Executive Summary\n\n" + "\n".join(summary_lines) + "\n\n"
        add(summary_text)

        # 제목 헤더
        add(f"{period_name} ICT 트렌드 분석 리포트\n{today}\n\n")

        # 역순 삽입 실행
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': blocks[::-1]}
        ).execute()

        # 공유 설정
        drive_service.permissions().create(
            fileId=doc_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        log_info(f"  ✅ 공유 드라이브 폴더에 구글 문서 생성 완료: {doc_url}")
        return doc_url, report_title

    except Exception as e:
        log_error(f"❌ 구글 문서 생성 실패: {e}")
        return None, None


# ==============================================================================
# --- 이메일 발송 ---
# ==============================================================================

@performance_monitor
def send_trend_report_email(
    report_title: str,
    analysis_result: Dict,
    doc_url: str,
    report_type: str = 'weekly',
    receivers: list = None,
):
    """트렌드 보고서 HTML 이메일 발송 (개조식, 링크 포함)"""
    from news_engine import SENDER_EMAIL, GMAIL_PASSWORD, RECEIVER_EMAIL
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formatdate

    log_info("📧 트렌드 보고서 이메일 발송 중...")

    period_name = "주간" if report_type == 'weekly' else "월간"
    stats = analysis_result.get('statistics', {})
    title_link_map = analysis_result.get('title_link_map', {})
    chain = analysis_result.get('_analysis_chain', 'AI 자동 분석')

    end_date = datetime.datetime.now()
    days = stats.get('period_days', 7)
    start_date = end_date - datetime.timedelta(days=days)
    period_text = f"{start_date.strftime('%Y.%m.%d')} - {end_date.strftime('%Y.%m.%d')}"

    # ── 헬퍼: 개조식 리스트 → HTML <ul> ─────────────────────────────────────
    def bullets_to_html(value, cls: str = '') -> str:
        lines = _bullet_lines(value)
        if not lines:
            return ''
        cls_attr = f' class="{cls}"' if cls else ''
        items = ''.join(f'<li{cls_attr}>{l[2:] if l.startswith("ㅇ ") else l}</li>' for l in lines)
        return f'<ul class="bullet-list">{items}</ul>'

    def related_articles_html(titles: List[str]) -> str:
        if not titles:
            return ''
        items = []
        for art in _resolve_article_links(titles, title_link_map):
            if art['link']:
                items.append(
                    f'<li><a href="{art["link"]}" target="_blank" class="news-link">'
                    f'{art["title"]}</a></li>'
                )
            else:
                items.append(f'<li class="news-link-plain">{art["title"]}</li>')
        return (
            '<div class="related-news">'
            '<span class="related-label">📰 관련 뉴스</span>'
            f'<ul>{"".join(items)}</ul>'
            '</div>'
        )

    # ── CSS ─────────────────────────────────────────────────────────────────
    css = """
        body { font-family:'Malgun Gothic','Segoe UI',sans-serif; line-height:1.7; color:#333;
               max-width:820px; margin:0 auto; padding:20px; background:#f5f7fa; }
        .header { background:linear-gradient(135deg,#667eea,#764ba2); color:white;
                  padding:40px 30px; border-radius:15px; text-align:center; margin-bottom:30px; }
        .header h1 { margin:0; font-size:26px; font-weight:700; }
        .header .period { margin-top:8px; font-size:14px; opacity:.9; }
        .header .chain { margin-top:6px; font-size:12px; opacity:.75; font-style:italic; }
        .stats-row { display:table; width:100%; border-collapse:separate; border-spacing:10px;
                     background:white; border-radius:12px; padding:15px; margin:20px 0;
                     box-shadow:0 2px 8px rgba(0,0,0,.07); }
        .stat-cell { display:table-cell; text-align:center; background:#f0f4ff;
                     border-radius:10px; padding:14px 10px; width:25%; }
        .stat-label { font-size:12px; color:#6c757d; font-weight:500; margin-bottom:4px; }
        .stat-value { font-size:28px; font-weight:700; color:#667eea; }
        .summary-box { background:#fff8e1; border:2px solid #ffc107; border-radius:12px;
                       padding:22px; margin:20px 0; }
        .summary-box h2 { margin:0 0 12px; font-size:17px; color:#e65100; }
        .bullet-list { margin:6px 0 6px 18px; padding:0; }
        .bullet-list li { margin-bottom:5px; font-size:14px; line-height:1.7; }
        .section { background:white; border-radius:12px; padding:22px; margin:20px 0;
                   box-shadow:0 2px 8px rgba(0,0,0,.07); }
        .section-title { font-size:19px; font-weight:700; color:#2c3e50; margin:0 0 16px;
                         padding-bottom:8px; border-bottom:3px solid #667eea; }
        .issue-card { border-radius:10px; padding:18px; margin:12px 0;
                      box-shadow:0 1px 6px rgba(0,0,0,.07); }
        .issue-card.high { border-left:5px solid #dc3545; }
        .issue-card.medium { border-left:5px solid #ffc107; }
        .issue-card.low { border-left:5px solid #28a745; }
        .issue-title { font-size:16px; font-weight:700; color:#2c3e50; margin-bottom:10px; }
        .meta-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; padding-top:10px;
                    border-top:1px solid #e9ecef; }
        .meta-tag { font-size:12px; background:#f0f4ff; border-radius:20px;
                    padding:3px 10px; color:#555; }
        .trend-card { background:#f0f4ff; border-left:4px solid #667eea; border-radius:8px;
                      padding:16px; margin:10px 0; }
        .trend-title { font-size:15px; font-weight:700; color:#1a237e; margin-bottom:8px; }
        .tech-card { background:#f1f8e9; border-left:4px solid #43a047; border-radius:8px;
                     padding:14px; margin:10px 0; }
        .tech-title { font-size:14px; font-weight:700; color:#2e7d32; margin-bottom:6px; }
        .related-news { margin-top:10px; padding:10px 12px; background:#fafafa;
                        border-radius:6px; border:1px solid #e0e0e0; }
        .related-label { font-size:12px; font-weight:600; color:#667eea; }
        .related-news ul { margin:4px 0 0 16px; padding:0; }
        .related-news li { font-size:12px; margin-bottom:3px; }
        .news-link { color:#667eea; text-decoration:none; }
        .news-link:hover { text-decoration:underline; }
        .news-link-plain { color:#555; }
        .insight-box { background:#e8f5e9; border-radius:10px; padding:18px; margin:16px 0; }
        .outlook-box { background:#fce4ec; border-radius:10px; padding:18px; margin:16px 0; }
        .doc-btn { display:inline-block; background:linear-gradient(135deg,#667eea,#764ba2);
                   color:white; padding:14px 32px; text-decoration:none; border-radius:25px;
                   font-weight:600; margin:25px 0; box-shadow:0 4px 14px rgba(102,126,234,.4); }
        .footer { margin-top:40px; padding:25px; background:linear-gradient(135deg,#2c3e50,#34495e);
                  border-radius:12px; text-align:center; color:white; font-size:13px; }
    """

    # ── 연속 이슈 HTML ──────────────────────────────────────────────────────
    def recurring_html() -> str:
        recurring = analysis_result.get('recurring_issues', [])
        if not recurring:
            return ''
        rows = ''
        for r in recurring:
            arrow = {'상승': '📈', '유지': '➡️', '하락': '📉', '신규': '🆕'}.get(
                r.get('trend_direction', ''), '')
            rows += (
                f'<tr>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e0e0e0;">{r["title"]}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e0e0e0;text-align:center;">'
                f'{r["occurrence_count"]}회</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e0e0e0;text-align:center;">'
                f'{r["impact_level"]}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e0e0e0;text-align:center;">'
                f'{arrow} {r.get("trend_direction","")}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e0e0e0;text-align:center;color:#888;">'
                f'{r.get("first_seen","")}</td>'
                f'</tr>'
            )
        return (
            '<div class="section" style="border-left:5px solid #ff9800;">'
            '<div class="section-title" style="border-bottom:3px solid #ff9800;">⚠️ 연속 등장 이슈</div>'
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="background:#fff3e0;">'
            '<th style="padding:6px 10px;text-align:left;">이슈</th>'
            '<th style="padding:6px 10px;">등장 횟수</th>'
            '<th style="padding:6px 10px;">중요도</th>'
            '<th style="padding:6px 10px;">추세</th>'
            '<th style="padding:6px 10px;">최초 감지</th>'
            '</tr></thead>'
            f'<tbody>{rows}</tbody>'
            '</table></div>'
        )

    # ── 핵심 이슈 HTML ───────────────────────────────────────────────────────
    def issues_html() -> str:
        html = ''
        for i, issue in enumerate(analysis_result.get('key_issues', [])[:7], 1):
            level = issue.get('impact_level', issue.get('importance', '하'))
            level_cls = 'high' if level == '상' else 'medium' if level == '중' else 'low'
            level_mark = '🔴' if level == '상' else '🟡' if level == '중' else '🟢'
            meta_parts = []
            if issue.get('tta_action_item'):
                meta_parts.append(f'<span class="meta-tag">💼 {issue["tta_action_item"][:40]}…</span>')
            if issue.get('standardization_gap'):
                meta_parts.append(f'<span class="meta-tag">📋 {issue["standardization_gap"][:40]}…</span>')
            if issue.get('tta_strategic_direction'):
                meta_parts.append(f'<span class="meta-tag">🎯 {issue["tta_strategic_direction"][:40]}…</span>')
            meta_html = f'<div class="meta-row">{"".join(meta_parts)}</div>' if meta_parts else ''
            html += (
                f'<div class="issue-card {level_cls}">'
                f'<div class="issue-title">{i}. {level_mark} {issue.get("title","")} <small style="color:#888;font-size:13px;">[영향도: {level}]</small></div>'
                f'{bullets_to_html(issue.get("description",[]))}'
                f'{meta_html}'
                f'{related_articles_html(issue.get("related_articles",[]))}'
                f'</div>'
            )
        return html

    # ── 트렌드 HTML ──────────────────────────────────────────────────────────
    def trends_html() -> str:
        html = ''
        for i, trend in enumerate(analysis_result.get('trends', [])[:5], 1):
            prediction_html = bullets_to_html(trend.get('prediction', []))
            html += (
                f'<div class="trend-card">'
                f'<div class="trend-title">Trend {i}. {trend.get("trend","")}</div>'
                f'{bullets_to_html(trend.get("description",[]))}'
                f'{prediction_html}'
                f'{related_articles_html(trend.get("related_articles",[]))}'
                f'</div>'
            )
        return html

    # ── 월간 전용 HTML ───────────────────────────────────────────────────────
    def monthly_extra_html() -> str:
        if report_type != 'monthly':
            return ''
        html = ''
        sf = analysis_result.get('standardization_focus', [])
        if sf:
            items = ''.join(
                f'<li><strong>{s.get("area","")}</strong><br>{bullets_to_html(s.get("reason",[]))}</li>'
                for s in sf
            )
            html += (
                '<div class="section">'
                '<div class="section-title">📐 표준화 집중 영역</div>'
                f'<ul style="padding-left:18px;">{items}</ul>'
                '</div>'
            )
        market = analysis_result.get('market_insights', [])
        if market:
            html += (
                '<div class="section">'
                '<div class="section-title">💼 시장 인사이트</div>'
                f'{bullets_to_html(market)}'
                '</div>'
            )
        return html

    # ── 전체 HTML 조립 ────────────────────────────────────────────────────────
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{css}</style></head>
<body>

<div class="header">
  <h1>📊 {period_name} ICT 트렌드 분석 리포트</h1>
  <div class="period">분석 기간: {period_text}</div>
  <div class="chain">분석 체계: {chain}</div>
</div>

<div class="stats-row">
  <div class="stat-cell"><div class="stat-label">전체 기사</div><div class="stat-value">{stats.get('total_articles',0)}</div></div>
  <div class="stat-cell"><div class="stat-label">분석 완료</div><div class="stat-value">{stats.get('analyzed_articles',0)}</div></div>
  <div class="stat-cell"><div class="stat-label">분석 기간</div><div class="stat-value">{stats.get('period_days',0)}일</div></div>
  <div class="stat-cell"><div class="stat-label">평균 품질</div><div class="stat-value">{stats.get('avg_quality_score',0)}</div></div>
</div>

<div class="summary-box">
  <h2>📌 Executive Summary</h2>
  {bullets_to_html(analysis_result.get('executive_summary',''))}
</div>

<div class="section">
  <div class="section-title">🔥 핵심 이슈</div>
  {issues_html()}
</div>

{recurring_html()}

<div class="section">
  <div class="section-title">📍 트렌드 분석</div>
  {trends_html()}
</div>

{monthly_extra_html()}

<div class="insight-box">
  <div class="section-title" style="border-bottom:2px solid #43a047;">🧠 인사이트</div>
  {bullets_to_html(analysis_result.get('insights',[]))}
</div>

<div class="outlook-box">
  <div class="section-title" style="border-bottom:2px solid #e91e63;">🔮 향후 전망</div>
  {bullets_to_html(analysis_result.get('outlook',[]))}
</div>

<div style="text-align:center;">
  <a href="{doc_url}" class="doc-btn" target="_blank">📄 전체 보고서 보기 (Google Docs)</a>
</div>

<div class="footer">
  <strong>한국정보통신기술협회(TTA)</strong> 표준화본부 이동통신표준팀<br>
  본 리포트는 IRONAGE AI Analytics System (v5.0)을 통해 자동 생성되었습니다.<br>
  © 2025 TTA. All rights reserved.
</div>

</body></html>"""

    # ── 발송 ─────────────────────────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["Subject"] = report_title
    msg["From"] = SENDER_EMAIL
    actual_receivers = list(receivers) if receivers else list(RECEIVER_EMAIL)
    msg["To"] = ", ".join(actual_receivers)
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, GMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, actual_receivers, msg.as_string())
        server.quit()
        log_info(f"  ✅ 이메일 발송 완료: {len(actual_receivers)}명")
    except Exception as e:
        log_error(f"❌ 이메일 발송 실패: {e}")


# ==============================================================================
# --- 이슈 연속성 추적 ---
# ==============================================================================

def _normalize_issue_key(title: str) -> str:
    """이슈 제목에서 비교용 키 추출 (공백·특수문자 제거, 소문자화)"""
    key = re.sub(r'[^\w가-힣]', '', title).lower()
    return key[:80]


@performance_monitor
def track_issue_continuity(
    current_issues: List[Dict],
    title_link_map: Dict[str, str],
    report_type: str = 'weekly',
) -> List[Dict]:
    """
    현재 이슈 목록을 IssueTracker DB에 기록하고,
    과거에 이미 등장한 이슈(연속 이슈)를 감지하여 반환한다.

    Returns:
        List[Dict]: 연속 등장 이슈 목록 (occurrence_count >= 2)
    """
    log_info("📌 이슈 연속성 추적 중...")
    now = datetime.datetime.now(datetime.timezone.utc)
    week_num = now.isocalendar()[1]
    escalated = []

    try:
        with get_db_session() as session:
            for issue in current_issues:
                key = _normalize_issue_key(issue.get('title', ''))
                if not key:
                    continue

                related_json = json.dumps(
                    [{'title': t, 'link': title_link_map.get(t, '')}
                     for t in issue.get('related_articles', [])],
                    ensure_ascii=False
                )
                level = issue.get('impact_level', issue.get('importance', '하'))

                existing = session.query(IssueTracker).filter_by(
                    issue_key=key
                ).order_by(IssueTracker.last_seen.desc()).first()

                if existing:
                    # 같은 주에 이미 기록됐으면 중복 방지
                    if existing.week_number == week_num and existing.report_type == report_type:
                        continue
                    existing.occurrence_count += 1
                    existing.last_seen = now
                    existing.week_number = week_num
                    existing.impact_level = level
                    existing.title = issue.get('title', existing.title)
                    existing.related_articles_json = related_json
                    existing.tta_action = issue.get('tta_action_item', existing.tta_action)

                    # 중요도 변화에 따른 추세 방향
                    _level_score = {'상': 3, '중': 2, '하': 1}
                    old_score = _level_score.get(existing.impact_level or '하', 1)
                    new_score = _level_score.get(level, 1)
                    existing.trend_direction = (
                        '상승' if new_score > old_score else
                        '하락' if new_score < old_score else '유지'
                    )

                    if existing.occurrence_count >= 2:
                        escalated.append({
                            'title': existing.title,
                            'occurrence_count': existing.occurrence_count,
                            'first_seen': existing.first_seen.strftime('%Y-%m-%d') if existing.first_seen else '',
                            'impact_level': level,
                            'trend_direction': existing.trend_direction,
                        })
                else:
                    session.add(IssueTracker(
                        issue_key=key,
                        title=issue.get('title', ''),
                        description=str(issue.get('description', '')),
                        impact_level=level,
                        report_type=report_type,
                        report_date=now,
                        week_number=week_num,
                        occurrence_count=1,
                        first_seen=now,
                        last_seen=now,
                        related_articles_json=related_json,
                        tta_action=issue.get('tta_action_item', ''),
                        trend_direction='신규',
                    ))

        log_info(f"  ✅ 이슈 추적 완료 — 연속 이슈 {len(escalated)}개 감지")
    except Exception as e:
        log_error(f"❌ 이슈 연속성 추적 실패: {e}")

    return escalated


def load_recurring_issues(min_count: int = 2, limit: int = 20) -> List[Dict]:
    """DB에서 반복 등장 이슈 목록 조회 (대시보드용)"""
    try:
        with get_db_session() as session:
            rows = (
                session.query(IssueTracker)
                .filter(IssueTracker.occurrence_count >= min_count)
                .order_by(IssueTracker.occurrence_count.desc(), IssueTracker.last_seen.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    'title': r.title,
                    'impact_level': r.impact_level,
                    'occurrence_count': r.occurrence_count,
                    'first_seen': r.first_seen.strftime('%Y-%m-%d') if r.first_seen else '',
                    'last_seen': r.last_seen.strftime('%Y-%m-%d') if r.last_seen else '',
                    'trend_direction': r.trend_direction,
                    'tta_action': r.tta_action,
                }
                for r in rows
            ]
    except Exception as e:
        log_error(f"❌ 반복 이슈 조회 실패: {e}")
        return []


# ==============================================================================
# --- 표준화 갭 누적 저장 ---
# ==============================================================================

@performance_monitor
def save_standardization_gaps(key_issues: List[Dict], report_type: str = 'weekly'):
    """
    핵심 이슈에서 표준화 공백(standardization_gap) 정보를 추출하여
    StandardizationGap 테이블에 누적 저장한다.
    """
    log_info("📐 표준화 갭 저장 중...")
    now = datetime.datetime.now(datetime.timezone.utc)
    saved = 0

    try:
        with get_db_session() as session:
            for issue in key_issues:
                gap_text = issue.get('standardization_gap', '').strip()
                if not gap_text or gap_text == 'N/A':
                    continue

                gap_key = re.sub(r'[^\w가-힣]', '', gap_text).lower()[:80]

                existing = session.query(StandardizationGap).filter(
                    StandardizationGap.area.like(f'%{gap_text[:30]}%')
                ).first()

                if existing:
                    existing.last_updated = now
                    existing.months_open = max(
                        0,
                        (now - (existing.first_detected or now)).days // 30
                    )
                    # 중요도 격상 시 업데이트
                    _prio = {'상': 3, '중': 2, '하': 1}
                    new_prio = issue.get('impact_level', '하')
                    if _prio.get(new_prio, 0) > _prio.get(existing.priority, 0):
                        existing.priority = new_prio
                else:
                    session.add(StandardizationGap(
                        area=gap_text[:300],
                        description=str(issue.get('description', '')),
                        source_issue_title=issue.get('title', '')[:500],
                        report_type=report_type,
                        report_date=now,
                        status='미해결',
                        priority=issue.get('impact_level', '중'),
                        months_open=0,
                        first_detected=now,
                        last_updated=now,
                    ))
                    saved += 1

        log_info(f"  ✅ 표준화 갭 저장 완료 — 신규 {saved}개")
    except Exception as e:
        log_error(f"❌ 표준화 갭 저장 실패: {e}")


def load_standardization_gaps(status: str = None, limit: int = 50) -> List[Dict]:
    """DB에서 표준화 갭 목록 조회 (대시보드용)"""
    try:
        with get_db_session() as session:
            q = session.query(StandardizationGap)
            if status:
                q = q.filter(StandardizationGap.status == status)
            rows = q.order_by(
                StandardizationGap.priority.desc(),
                StandardizationGap.months_open.desc()
            ).limit(limit).all()
            return [
                {
                    'id': r.id,
                    'area': r.area,
                    'priority': r.priority,
                    'status': r.status,
                    'months_open': r.months_open,
                    'source_issue': r.source_issue_title,
                    'first_detected': r.first_detected.strftime('%Y-%m-%d') if r.first_detected else '',
                    'last_updated': r.last_updated.strftime('%Y-%m-%d') if r.last_updated else '',
                    'resolution_note': r.resolution_note or '',
                }
                for r in rows
            ]
    except Exception as e:
        log_error(f"❌ 표준화 갭 조회 실패: {e}")
        return []


def update_gap_status(gap_id: int, status: str, resolution_note: str = ''):
    """표준화 갭 상태 업데이트"""
    try:
        with get_db_session() as session:
            gap = session.query(StandardizationGap).get(gap_id)
            if gap:
                gap.status = status
                gap.resolution_note = resolution_note
                gap.last_updated = datetime.datetime.now(datetime.timezone.utc)
        log_info(f"  ✅ 갭 #{gap_id} 상태 업데이트: {status}")
    except Exception as e:
        log_error(f"❌ 갭 상태 업데이트 실패: {e}")


# ==============================================================================
# --- 로컬 마크다운 보고서 저장 ---
# ==============================================================================

@performance_monitor
def save_report_to_markdown(
    analysis_result: Dict,
    report_type: str = 'weekly',
    auto_intel_state: Optional[Dict] = None
) -> Optional[str]:
    """
    트렌드 분석 결과를 마크다운 파일로 로컬 results/ 폴더에 저장한다.
    파일명 형식: results/[YYMMDD]_[보고서종류].md
    예: 260522_주간트렌드분석.md
    """
    import os
    from typing import Optional
    
    log_info("💾 로컬 마크다운 보고서 저장 중...")
    try:
        # 1. 디렉토리 생성
        output_dir = "results"
        os.makedirs(output_dir, exist_ok=True)
        
        # 2. 파일명 결정 ([YYMMDD]_[보고서종류].md)
        today_str = datetime.datetime.now().strftime('%y%m%d')  # YYMMDD
        
        if auto_intel_state:
            report_kind = "자율인텔리전스_주간" if report_type == 'weekly' else "자율인텔리전스_월간"
        else:
            report_kind = "주간트렌드분석" if report_type == 'weekly' else "월간인텔리전스"
            
        file_name = f"{today_str}_{report_kind}.md"
        file_path = os.path.join(output_dir, file_name)
        
        # 3. 마크다운 본문 구성
        period_name = "주간" if report_type == 'weekly' else "월간"
        today_full = datetime.datetime.now().strftime('%Y년 %m월 %d일')
        
        title_link_map = analysis_result.get('title_link_map', {})
        stats = analysis_result.get('statistics', {})
        chain = analysis_result.get('_analysis_chain', 'AI 자동 분석')
        
        md_lines = []
        md_lines.append(f"# [TTA] {period_name} ICT 트렌드 분석 보고서 ({today_full})")
        md_lines.append(f"\n- **분석 체계:** {chain}")
        
        if auto_intel_state and auto_intel_state.get('doc_url'):
            md_lines.append(f"- **구글 문서 링크:** [{auto_intel_state.get('doc_url')}]({auto_intel_state.get('doc_url')})")
        
        md_lines.append("\n---")
        
        # Executive Summary
        md_lines.append("\n## 📊 Executive Summary")
        summary_lines = _bullet_lines(analysis_result.get('executive_summary', ''))
        for line in summary_lines:
            md_lines.append(line)
            
        # 통계
        md_lines.append("\n## 📈 주요 통계")
        md_lines.append(f"- **전체 기사 수:** {stats.get('total_articles', 0)}개")
        md_lines.append(f"- **분석 완료 기사 수:** {stats.get('analyzed_articles', 0)}개")
        md_lines.append(f"- **평균 품질 점수:** {stats.get('avg_quality_score', 0)}")
        source_dist = stats.get('source_distribution', {})
        if source_dist:
            md_lines.append(f"- **주요 출처:** {', '.join(list(source_dist.keys())[:5])}")
            
        # 자율 인텔리전스 - 급등 엔티티 분석 추가
        if auto_intel_state and auto_intel_state.get('surges'):
            md_lines.append("\n## 📈 급등 엔티티 심층 분석 (자율 인텔리전스)")
            md_lines.append("\n### 【 이번 기간 급등 엔티티 】")
            type_label = {'company': '기업', 'tech': '기술', 'country': '국가'}
            for s in auto_intel_state['surges']:
                pct = s['pct_change']
                pct_str = f"+{pct*100:.0f}%" if pct != float('inf') else "신규 등장"
                label = type_label.get(s['node_type'], '')
                md_lines.append(f"- **{s['name']}** ({label}, {pct_str}): {s['prev_count']} → {s['curr_count']}회")
                
            if auto_intel_state.get('surge_narrative'):
                md_lines.append("\n### 【 AI 종합 분석 】")
                md_lines.append(auto_intel_state['surge_narrative'])
                
            if auto_intel_state.get('rag_context'):
                md_lines.append("\n### 【 엔티티별 RAG 심층 분석 】")
                for s in auto_intel_state['surges']:
                    rag = auto_intel_state['rag_context'].get(s['name'], {})
                    answer = rag.get('answer', '').strip()
                    if answer:
                        md_lines.append(f"\n#### **{s['name']}**")
                        md_lines.append(answer)
            md_lines.append("\n---")
            
        # 핵심 이슈
        md_lines.append("\n## 🔥 핵심 이슈")
        issues = analysis_result.get('key_issues', [])
        for i, issue in enumerate(issues, 1):
            level = issue.get('impact_level', issue.get('importance', '하'))
            level_mark = "🔴" if level == '상' else "🟡" if level == '중' else "🟢"
            md_lines.append(f"\n### {i}. {level_mark} {issue.get('title', '')} [영향도: {level}]")
            for line in _bullet_lines(issue.get('description', [])):
                md_lines.append(f"  {line}")
            if issue.get('standardization_gap'):
                md_lines.append(f"  - **[표준화 공백]** {issue['standardization_gap']}")
            if issue.get('tta_action_item'):
                md_lines.append(f"  - **[TTA 대응]** {issue['tta_action_item']}")
            if issue.get('weekly_evolution'):
                md_lines.append(f"  - **[이슈 추이]** {issue['weekly_evolution']}")
            if issue.get('tta_strategic_direction'):
                md_lines.append(f"  - **[전략 방향]** {issue['tta_strategic_direction']}")
            related = _resolve_article_links(issue.get('related_articles', []), title_link_map)
            if related:
                md_lines.append("  - **[관련 뉴스]**")
                for art in related:
                    link_str = f" ([링크]({art['link']}))" if art['link'] else ""
                    md_lines.append(f"    - {art['title']}{link_str}")
                    
        # 연속 이슈 알림 섹션
        recurring = analysis_result.get('recurring_issues', [])
        if recurring:
            md_lines.append("\n## ⚠️ 연속 등장 이슈 (주의 필요)")
            for r in recurring:
                arrow = {'상승': '📈', '유지': '➡️', '하락': '📉', '신규': '🆕'}.get(
                    r.get('trend_direction', ''), '•')
                md_lines.append(
                    f"- **{r['title']}** "
                    f"({r['occurrence_count']}회 연속 | 중요도: {r['impact_level']} | "
                    f"추세: {arrow} {r.get('trend_direction','')} | "
                    f"최초 감지: {r.get('first_seen','')})"
                )
                
        # 트렌드 분석
        trends = analysis_result.get('trends', [])
        if trends:
            md_lines.append("\n## 📍 트렌드 분석")
            for i, trend in enumerate(trends, 1):
                md_lines.append(f"\n### Trend {i}. {trend.get('trend', '')}")
                for line in _bullet_lines(trend.get('description', [])):
                    md_lines.append(f"  {line}")
                for line in _bullet_lines(trend.get('prediction', [])):
                    md_lines.append(f"  {line}")
                related = _resolve_article_links(trend.get('related_articles', []), title_link_map)
                if related:
                    md_lines.append("  - **[관련 뉴스]**")
                    for art in related:
                        link_str = f" ([링크]({art['link']}))" if art['link'] else ""
                        md_lines.append(f"    - {art['title']}{link_str}")
                        
        # 월간 전용 섹션
        if report_type == 'monthly':
            # 표준화 집중 영역
            sf_list = analysis_result.get('standardization_focus', [])
            if sf_list:
                md_lines.append("\n## 📐 표준화 집중 영역")
                for sf in sf_list:
                    md_lines.append(f"\n### ■ {sf.get('area', '')}")
                    for line in _bullet_lines(sf.get('reason', [])):
                        md_lines.append(f"  {line}")
                        
            # 시장 인사이트
            market = _bullet_lines(analysis_result.get('market_insights', []))
            if market:
                md_lines.append("\n## 💼 시장 인사이트")
                for line in market:
                    md_lines.append(line)
                    
        # 인사이트
        insights = _bullet_lines(analysis_result.get('insights', []))
        if insights:
            md_lines.append("\n## 💡 인사이트")
            for line in insights:
                md_lines.append(line)
                
        # 향후 전망
        outlook = _bullet_lines(analysis_result.get('outlook', []))
        if outlook:
            md_lines.append("\n## 🔮 향후 전망")
            for line in outlook:
                md_lines.append(line)
                
        # 푸터
        md_lines.append("\n---")
        md_lines.append("\n**한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀**  ")
        md_lines.append("본 보고서는 IRONAGE AI Analytics System (v5.0)으로 자동 생성되었습니다.  ")
        
        # 파일 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
            
        log_info(f"  ✅ 로컬 마크다운 보고서 저장 완료: {file_path}")
        return file_path
        
    except Exception as e:
        log_error(f"❌ 로컬 마크다운 보고서 저장 실패: {e}")
        return None


# ==============================================================================
# --- 로컬 심층분석 마크다운 보고서 저장 ---
# ==============================================================================

@performance_monitor
def save_analyzed_news_to_markdown(analyzed_data: List[Dict]) -> Optional[str]:
    """
    수동 뉴스 심층 분석 결과를 마크다운 파일로 로컬 results/ 폴더에 저장한다.
    파일명 형식: results/[YYMMDD]_심층분석보고서.md
    """
    import os
    from typing import Optional
    
    log_info("💾 로컬 심층분석 마크다운 보고서 저장 중...")
    try:
        # 1. 디렉토리 생성
        output_dir = "results"
        os.makedirs(output_dir, exist_ok=True)
        
        # 2. 파일명 결정
        today_str = datetime.datetime.now().strftime('%y%m%d')  # YYMMDD
        file_name = f"{today_str}_심층분석보고서.md"
        file_path = os.path.join(output_dir, file_name)
        
        # 3. 마크다운 본문 구성
        today_full = datetime.datetime.now().strftime('%Y년 %m월 %d일')
        
        md_lines = []
        md_lines.append(f"# 전파·이동통신 동향 보고서 ({today_full})")
        md_lines.append(f"\n- **작성일:** {datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}")
        md_lines.append("- **작성 기관:** 한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀")
        md_lines.append("\n---")
        
        # 안내사항
        md_lines.append("\n## 📌 안내사항")
        md_lines.append("> 본 보고서는 IRONAGE AI Analytics System이 자동으로 생성한 분석 보고서입니다. AI가 수집한 뉴스를 기반으로 작성되었습니다.")
        
        # Phase 7: 전주 대비 급등 키워드 TOP 5 섹션
        try:
            from knowledge_graph import detect_surge_entities
            _now = datetime.datetime.now()
            _prev_start = _now - datetime.timedelta(days=14)
            _prev_end = _now - datetime.timedelta(days=7)
            
            # DB 세션
            from news_engine import get_db_session, NewsArticle
            with get_db_session() as _db:
                _prev_rows = _db.query(NewsArticle).filter(
                    NewsArticle.collected_at >= _prev_start,
                    NewsArticle.collected_at < _prev_end
                ).all()
                _prev_data = [
                    {
                        'title': a.title or '',
                        'analysis_result': a.analysis_result or '',
                        'extracted_keywords': a.extracted_keywords or '',
                    }
                    for a in _prev_rows
                ]
            _surge_entities = detect_surge_entities(analyzed_data, _prev_data)[:5]
            if _surge_entities:
                md_lines.append("\n## 📈 전주 대비 급등 키워드 TOP 5")
                for _rank, _ent in enumerate(_surge_entities, 1):
                    _name = _ent.get('name', '')
                    _ntype = _ent.get('node_type', '')
                    _prev_c = _ent.get('prev_count', 0)
                    _curr_c = _ent.get('curr_count', 0)
                    _pct = _ent.get('pct_change', 0)
                    if _pct == float('inf'):
                        _pct_str = "신규 등장"
                    else:
                        _pct_str = f"+{_pct*100:.0f}%" if _pct >= 0 else f"{_pct*100:.0f}%"
                    md_lines.append(f"- **{_name}** ({_ntype}) | 전주 {_prev_c}회 → 이번주 {_curr_c}회 ({_pct_str})")
        except Exception as _e:
            log_warning(f"급등 키워드 섹션 생성 실패: {_e}")
            
        # 목차
        md_lines.append("\n## 📋 목차")
        for i, data in enumerate(analyzed_data[:10], 1):
            md_lines.append(f"{i}. {data['title'][:60]}...")
            
        # 영향도 요약 섹션 (Critical / High)
        from news_engine import _get_impact_info, IMPACT_LEVEL_ICON, IMPACT_LEVEL_ORDER
        critical_high = [
            (d, _get_impact_info(d))
            for d in analyzed_data
            if _get_impact_info(d)['impact_level'] in ('Critical', 'High')
        ]
        critical_high.sort(key=lambda x: IMPACT_LEVEL_ORDER.get(x[1]['impact_level'], 2))
        
        if critical_high:
            md_lines.append("\n## 🔔 주요 조치 필요 항목 (Critical / High)")
            for art, info in critical_high:
                icon = IMPACT_LEVEL_ICON.get(info['impact_level'], '📋')
                level = info['impact_level']
                tta = info['tta_action_item'] or '추가 모니터링 필요'
                md_lines.append(f"- {icon} **[{level}]** {art['title'][:80]}  \n  → **TTA 조치:** {tta}")
                
        # 각 뉴스 아이템 상세 분석
        md_lines.append("\n## 📰 상세 뉴스 분석")
        for i, data in enumerate(analyzed_data, 1):
            md_lines.append(f"\n### 【 {i} 】 {data['title']}")
            md_lines.append(f"- **출처:** {data['source']} | **발행일:** {data['published']}")
            md_lines.append(f"- **원문 링크:** [{data['link']}]({data['link']})")
            
            impact_info = _get_impact_info(data)
            impact_level = impact_info['impact_level']
            impact_icon = IMPACT_LEVEL_ICON.get(impact_level, '📋')
            md_lines.append(f"- **{impact_icon} 영향도:** {impact_level}")
            
            if impact_info.get('tta_action_item'):
                md_lines.append(f"- **💼 TTA 조치 사항:** {impact_info['tta_action_item']}")
            if impact_info.get('standardization_gap'):
                md_lines.append(f"- **📐 표준화 공백 영역:** {impact_info['standardization_gap']}")
                
            md_lines.append("\n**📝 AI 분석 내용:**")
            analysis_text = data.get('analysis_result', '').strip()
            if analysis_text:
                md_lines.append(analysis_text)
            else:
                md_lines.append("상세 분석 내용이 없습니다.")
            md_lines.append("\n---")
            
        # 파일 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
            
        log_info(f"  ✅ 로컬 심층분석 마크다운 보고서 저장 완료: {file_path}")
        return file_path
        
    except Exception as e:
        log_error(f"❌ 로컬 심층분석 마크다운 보고서 저장 실패: {e}")
        return None
