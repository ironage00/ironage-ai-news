"""
IRONAGE AI Analytics System v5.0
자율 인텔리전스 리포트 오케스트레이터 (Phase 4)

LangGraph 개념의 상태 기계(state machine)를 순수 Python으로 구현.
각 노드는 State dict를 받아 변환하고 반환한다.

노드 흐름:
  load_data → detect_surges → rag_retrieve → gen_narrative
            → build_report → append_to_doc → send_report

실제 LangGraph 마이그레이션 시 각 node_* 함수를 그대로 add_node()에 등록하면 됨.
"""

import datetime
import json
import re
import pytz
from typing import Any, Callable, Dict, List, Optional

_KST_TZ = pytz.timezone('Asia/Seoul')


def _now_kst() -> datetime.datetime:
    return datetime.datetime.now(_KST_TZ)

from news_engine import (
    load_news_from_db,
    get_openai_client,
    OPENAI_MODEL_DEFAULT,
    log_info,
    log_warning,
    log_error,
)

# ==============================================================================
# --- 상태 타입 ---
# ==============================================================================

def make_state(
    period: str = 'weekly',
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """초기 State dict 생성."""
    days = 7 if period == 'weekly' else 30
    return {
        'period':         period,
        'days':           days,
        'news_current':   [],
        'news_prev':      [],
        'surges':         [],
        'rag_context':    {},    # {entity_name: {'answer': str, 'sources': list}}
        'surge_narrative': '',
        'analysis_result': {},
        'doc_url':        None,
        'doc_id':         None,
        'report_title':   '',
        'email_sent':     False,
        'log':            [],
        'errors':         [],
        '_progress_cb':   progress_cb or (lambda msg: None),
    }


def _log(state: Dict, msg: str):
    state['log'].append(msg)
    state['_progress_cb'](msg)
    log_info(msg)


# ==============================================================================
# --- 노드 함수들 ---
# ==============================================================================

def node_load_data(state: Dict) -> Dict:
    """현재 기간 + 이전 기간 뉴스 로드."""
    days = state['days']
    _log(state, f"[1/7] 뉴스 데이터 로드 중 (최근 {days}일 + 이전 {days}일)...")

    news_current = [
        n for n in load_news_from_db(days=days, is_analyzed=True)
        if n.get('extracted_keywords')
    ]

    cutoff = _now_kst() - datetime.timedelta(days=days)
    news_all_prev = load_news_from_db(days=days * 2, is_analyzed=True)
    news_prev = [
        n for n in news_all_prev
        if n.get('extracted_keywords') and _before(n.get('collected_at'), cutoff)
    ]

    state['news_current'] = news_current
    state['news_prev'] = news_prev
    _log(state, f"  ✅ 현재: {len(news_current)}개 / 이전: {len(news_prev)}개")
    return state


def _before(ts_val, cutoff: datetime.datetime) -> bool:
    if ts_val is None:
        return False
    try:
        if isinstance(ts_val, datetime.datetime):
            return ts_val < cutoff
        return str(ts_val) < str(cutoff)
    except Exception:
        return False


def node_detect_surges(state: Dict) -> Dict:
    """이전 기간 대비 급등 엔티티 감지."""
    _log(state, "[2/7] 급등 엔티티 감지 중...")
    try:
        from knowledge_graph import detect_surge_entities
        surges = detect_surge_entities(
            news_current=state['news_current'],
            news_prev=state['news_prev'],
            threshold=0.5,
            min_current=2,
        )
        state['surges'] = surges[:6]   # 최대 6개
        if surges:
            names = ', '.join(s['name'] for s in state['surges'])
            _log(state, f"  ✅ 급등 엔티티 {len(state['surges'])}개: {names}")
        else:
            _log(state, "  ℹ️  급등 엔티티 없음 (이전 기간 데이터 부족 가능)")
    except Exception as e:
        log_warning(f"급등 감지 실패: {e}")
        state['errors'].append(f"surge_detect: {e}")
    return state


def node_rag_retrieve(state: Dict) -> Dict:
    """급등 엔티티별 RAG 검색으로 관련 기사 컨텍스트 수집."""
    if not state['surges']:
        _log(state, "[3/7] 급등 엔티티 없음 — RAG 검색 건너뜀")
        return state

    _log(state, f"[3/7] 급등 엔티티 {len(state['surges'])}개 RAG 검색 중...")
    try:
        from rag_search import answer_with_rag, embed_unprocessed_articles
        embed_unprocessed_articles(limit=50)   # 미임베딩 기사 처리

        for surge in state['surges']:
            name = surge['name']
            query = f"{name} 관련 최신 동향 및 표준화 시사점"
            try:
                result = answer_with_rag(query, top_k=3, days=state['days'])
                state['rag_context'][name] = result
                _log(state, f"  ✅ [{name}] RAG 답변 생성")
            except Exception as e:
                log_warning(f"RAG 실패 [{name}]: {e}")
                state['rag_context'][name] = {'answer': '', 'sources': [], 'query': query}

    except ImportError as e:
        log_warning(f"RAG 모듈 없음: {e}")
        state['errors'].append(f"rag_import: {e}")

    return state


def node_gen_narrative(state: Dict) -> Dict:
    """GPT-4o로 급등 엔티티 통합 내러티브 생성."""
    if not state['surges']:
        _log(state, "[4/7] 급등 엔티티 없음 — 내러티브 생성 건너뜀")
        return state

    _log(state, "[4/7] AI 급등 내러티브 생성 중...")
    try:
        client = get_openai_client()

        surge_lines = []
        for s in state['surges']:
            pct = s['pct_change']
            pct_str = f"+{pct*100:.0f}%" if pct != float('inf') else "신규 등장"
            rag = state['rag_context'].get(s['name'], {})
            answer = rag.get('answer', '').strip()
            surge_lines.append(
                f"- [{s['name']}] ({s['node_type']}) {pct_str} "
                f"({s['prev_count']}→{s['curr_count']}회)\n  RAG 분석: {answer[:300] if answer else '없음'}"
            )

        period_name = "주간" if state['period'] == 'weekly' else "월간"
        prompt = f"""당신은 TTA(한국정보통신기술협회) ICT 트렌드 분석 전문가입니다.

이번 {period_name} 급등 엔티티 목록과 RAG 분석 결과를 바탕으로,
TTA 표준화 관점에서의 시사점을 포함한 종합 분석을 작성하세요.

[급등 엔티티 현황]
{chr(10).join(surge_lines)}

[작성 규칙]
- 개조식(ㅇ) 형식으로 3~5개 핵심 포인트 작성
- 각 포인트에 엔티티 이름을 명시
- TTA 표준화 시사점 포함
- 한국어, 300자 이내

[출력 형식]
ㅇ (내용)
ㅇ (내용)
...
"""
        resp = client.chat.completions.create(
            model=OPENAI_MODEL_DEFAULT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )
        state['surge_narrative'] = resp.choices[0].message.content.strip()
        _log(state, "  ✅ 급등 내러티브 생성 완료")

    except Exception as e:
        log_warning(f"내러티브 생성 실패: {e}")
        state['errors'].append(f"narrative: {e}")
        # 폴백: 단순 목록으로 대체
        lines = []
        for s in state['surges']:
            pct = s['pct_change']
            pct_str = f"+{pct*100:.0f}%" if pct != float('inf') else "신규 등장"
            lines.append(f"ㅇ {s['name']} ({pct_str}) — 집중 모니터링 필요")
        state['surge_narrative'] = '\n'.join(lines)

    return state


def node_build_report(state: Dict) -> Dict:
    """기존 트렌드 분석 파이프라인으로 베이스 리포트 생성."""
    _log(state, "[5/7] 베이스 트렌드 리포트 생성 중...")
    try:
        period = state['period']
        articles = state['news_current']

        if not articles:
            state['errors'].append("build_report: 뉴스 없음")
            return state

        if period == 'weekly':
            from trend_analyzer import analyze_weekly_trends, generate_trend_report_doc, send_trend_report_email
            analysis = analyze_weekly_trends(articles)
        else:
            from trend_analyzer import analyze_monthly_trends, generate_trend_report_doc, send_trend_report_email
            analysis = analyze_monthly_trends(articles)

        if not analysis:
            state['errors'].append("build_report: 분석 결과 없음")
            return state

        state['analysis_result'] = analysis
        doc_url, report_title = generate_trend_report_doc(analysis, report_type=period)
        state['doc_url'] = doc_url
        state['report_title'] = report_title

        # doc_id 추출
        if doc_url:
            m = re.search(r'/d/([a-zA-Z0-9_-]+)', doc_url)
            if m:
                state['doc_id'] = m.group(1)

        _log(state, f"  ✅ 베이스 리포트 생성: {doc_url}")

    except Exception as e:
        log_error(f"베이스 리포트 생성 실패: {e}")
        state['errors'].append(f"build_report: {e}")

    return state


def node_append_to_doc(state: Dict) -> Dict:
    """생성된 Google Doc에 급등 엔티티 심층 분석 섹션 추가."""
    if not state.get('doc_id') or not state['surges']:
        _log(state, "[6/7] 문서 추가 건너뜀 (doc_id 없거나 급등 엔티티 없음)")
        return state

    _log(state, "[6/7] 급등 엔티티 심층 분석 섹션 추가 중...")
    try:
        from news_engine import get_google_docs_service
        docs_service, _ = get_google_docs_service()

        # 급등 섹션 텍스트 구성
        type_label = {'company': '기업', 'tech': '기술', 'country': '국가'}
        surge_lines = []
        for s in state['surges']:
            pct = s['pct_change']
            pct_str = f"+{pct*100:.0f}%" if pct != float('inf') else "신규 등장"
            label = type_label.get(s['node_type'], '')
            surge_lines.append(
                f"  • {s['name']} ({label}, {pct_str}): "
                f"{s['prev_count']}→{s['curr_count']}회"
            )

        rag_detail_lines = []
        for s in state['surges']:
            rag = state['rag_context'].get(s['name'], {})
            answer = rag.get('answer', '').strip()
            if answer:
                rag_detail_lines.append(f"\n[{s['name']}]\n{answer[:400]}")

        section_text = (
            "\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📈 급등 엔티티 심층 분석 (자율 인텔리전스)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "【 이번 기간 급등 엔티티 】\n"
            + '\n'.join(surge_lines)
            + "\n\n【 AI 종합 분석 】\n"
            + state['surge_narrative']
            + ("\n\n【 엔티티별 RAG 심층 분석 】\n" + '\n'.join(rag_detail_lines) if rag_detail_lines else "")
            + "\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "본 섹션은 IRONAGE AI Analytics System v5.0 자율 인텔리전스 모듈이 자동 생성\n"
        )

        # 문서 끝에 삽입 (index 1 = 문서 앞에 삽입하는 Docs API 방식)
        docs_service.documents().batchUpdate(
            documentId=state['doc_id'],
            body={
                'requests': [
                    {
                        'insertText': {
                            'location': {'index': 1},
                            'text': section_text,
                        }
                    }
                ]
            }
        ).execute()

        _log(state, "  ✅ 급등 분석 섹션 Google Doc에 추가 완료")

    except Exception as e:
        log_warning(f"Google Doc 추가 실패: {e}")
        state['errors'].append(f"append_doc: {e}")

    return state


def node_send_report(state: Dict) -> Dict:
    """이메일 발송 (급등 섹션 포함)."""
    if not state.get('doc_url'):
        _log(state, "[7/7] doc_url 없음 — 이메일 건너뜀")
        return state

    _log(state, "[7/7] 이메일 발송 중...")
    try:
        from trend_analyzer import send_trend_report_email
        analysis = state['analysis_result']

        # 급등 요약을 analysis_result에 주입 (이메일 subject line용)
        if state['surges']:
            top = state['surges'][0]
            pct = top['pct_change']
            pct_str = f"+{pct*100:.0f}%" if pct != float('inf') else "신규"
            analysis['_surge_summary'] = f"급등: {top['name']} ({pct_str})"

        send_trend_report_email(
            state['report_title'],
            analysis,
            state['doc_url'],
            report_type=state['period'],
        )
        state['email_sent'] = True
        _log(state, "  ✅ 이메일 발송 완료")

    except Exception as e:
        log_warning(f"이메일 발송 실패: {e}")
        state['errors'].append(f"send_email: {e}")

    return state


# ==============================================================================
# --- 오케스트레이터 ---
# ==============================================================================

_PIPELINE = [
    node_load_data,
    node_detect_surges,
    node_rag_retrieve,
    node_gen_narrative,
    node_build_report,
    node_append_to_doc,
    node_send_report,
]


def run_auto_intel_report(
    period: str = 'weekly',
    progress_cb: Optional[Callable[[str], None]] = None,
    skip_email: bool = False,
) -> Dict[str, Any]:
    """
    자율 인텔리전스 리포트 전체 파이프라인 실행.

    Args:
        period:      'weekly' | 'monthly'
        progress_cb: 진행 상황 콜백 (Streamlit st.write 등)
        skip_email:  True이면 이메일 발송 건너뜀 (테스트용)

    Returns:
        최종 State dict
    """
    state = make_state(period=period, progress_cb=progress_cb)
    pipeline = _PIPELINE[:-1] if skip_email else _PIPELINE

    for node_fn in pipeline:
        try:
            state = node_fn(state)
        except Exception as e:
            log_error(f"노드 {node_fn.__name__} 치명적 오류: {e}")
            state['errors'].append(f"{node_fn.__name__}: {e}")
            break   # 후속 노드 실행 중단

    # ✅ 로컬 마크다운 파일 저장 (results/ 폴더 및 규약 적용)
    if state.get('analysis_result'):
        try:
            from trend_analyzer import save_report_to_markdown
            md_path = save_report_to_markdown(
                analysis_result=state['analysis_result'],
                report_type=period,
                auto_intel_state=state
            )
            if md_path:
                _log(state, f"  💾 [로컬 저장 완료] {md_path}")
            else:
                _log(state, "  ⚠️ [로컬 저장 실패] 마크다운 파일이 저장되지 않았습니다.")
        except Exception as e:
            log_warning(f"로컬 마크다운 저장 중 예외 발생: {e}")
            state['errors'].append(f"local_markdown_save: {e}")

    # 결과 요약 로그
    _log(state, f"\n{'='*50}")
    _log(state, f"✅ 자율 인텔리전스 리포트 완료")
    _log(state, f"   급등 엔티티: {len(state['surges'])}개")
    _log(state, f"   문서 URL: {state.get('doc_url', '없음')}")
    _log(state, f"   이메일 발송: {'✅' if state['email_sent'] else '건너뜀'}")
    if state['errors']:
        _log(state, f"   경고/오류: {', '.join(state['errors'])}")
    _log(state, f"{'='*50}")

    return state


if __name__ == '__main__':
    import sys
    import io
    
    # Windows 한글 출력 인코딩 방어
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    log_info("🚀 자율 인텔리전스 리포트 CLI 실행기 기동")
    
    import argparse
    parser = argparse.ArgumentParser(description="IRONAGE AI 자율 인텔리전스 리포트 CLI")
    parser.add_argument('--period', type=str, default='weekly', choices=['weekly', 'monthly'], help="리포트 기간 (weekly 또는 monthly)")
    parser.add_argument('--skip-email', action='store_true', help="이메일 발송 단계 생략 (테스트용)")
    args = parser.parse_args()
    
    log_info(f"👉 설정: 기간={args.period}, 이메일생략={args.skip_email}")
    run_auto_intel_report(period=args.period, skip_email=args.skip_email)
