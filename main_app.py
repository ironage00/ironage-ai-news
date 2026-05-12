"""
IRONAGE AI Analytics System v5.0
Streamlit 웹 대시보드 - 완전판 (수정 버전)
"""

import sys
import subprocess
from pathlib import Path
import json
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from streamlit_option_menu import option_menu
import streamlit as st
import warnings
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
from io import BytesIO
import traceback 

warnings.filterwarnings('ignore')

# news_engine 모듈 import
sys.path.append('.')

try:
    from news_engine import (
        # 함수들
        get_db_statistics,
        load_news_from_db,
        run_daily_collection,
        run_weekly_report,
        run_monthly_report,
        analyze_news_with_ai,
        analyze_news_with_replacement,
        update_analysis_in_db,
        get_news_data,
        save_news_to_db,
        filter_news_by_ai,
        get_article_content,
        is_valid_analysis,
        generate_google_doc_report,
        send_gmail_report,
        verify_deduplication,
        save_analysis_to_weekly_excel,
        save_keyword_summary_to_weekly_excel,
        get_week_number,
        get_week_date_range,
        get_db_session,
        clear_clients_cache,
        check_model_health,
        _get_impact_info,
        load_user_settings,
        save_user_settings,
        IMPACT_LEVEL_ORDER,
        IMPACT_LEVEL_COLOR_RGB,

        # 데이터베이스
        SessionLocal,
        NewsArticle,

        # 설정 변수들
        OPENAI_API_KEY,
        NAVER_CLIENT_ID,
        NAVER_CLIENT_SECRET,
        SENDER_EMAIL,
        GMAIL_PASSWORD,
        RECEIVER_EMAIL,
        GOOGLE_ALERTS_RSS_URLS,
        NAVER_QUERIES
    )
except ImportError as e:
    st.error(f"❌ 모듈 import 실패: {e}")
    st.info("news_engine.py 파일이 같은 폴더에 있는지 확인하세요.")
    st.stop()

# ===== 페이지 설정 =====
st.set_page_config(
    page_title="IRONAGE AI Analytics",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== Google OAuth 인증 =====
# Streamlit Community Cloud 환경에서는 st.experimental_user가 활성화됨.
# 로컬 개발 환경에서는 is_logged_in이 없으므로 hasattr로 확인.
_auth_enabled = hasattr(st.experimental_user, 'is_logged_in')

if _auth_enabled:
    if not st.experimental_user.is_logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("## IRONAGE AI Analytics")
            st.markdown("### TTA ICT 뉴스 인텔리전스 시스템")
            st.markdown("---")
            if st.button("🔑 Google 계정으로 로그인", use_container_width=True, type="primary"):
                st.login()
            st.caption("@tta.or.kr 계정만 접속 가능합니다.")
        st.stop()

    _user_email = st.experimental_user.email or ""
    _user_name  = st.experimental_user.name  or _user_email

    if not _user_email.endswith("@tta.or.kr"):
        st.error(f"접근 거부: {_user_email} 은(는) TTA 임직원 계정이 아닙니다.")
        st.info("@tta.or.kr 계정으로 다시 로그인해 주세요.")
        if st.button("로그아웃"):
            st.logout()
        st.stop()
else:
    # 로컬 개발 모드 — 인증 없이 통과
    _user_email = "local@tta.or.kr"
    _user_name  = "로컬 개발자"


# ===== 헬퍼 함수 정의 (함수 호출 전에 정의) =====
# get_db_session은 news_engine에서 임포트


def log_info(message: str):
    """정보 로그 출력"""
    print(f"[INFO] {message}")


def log_warning(message: str):
    """경고 로그 출력"""
    print(f"[WARNING] {message}")


def log_error(message: str):
    """에러 로그 출력"""
    print(f"[ERROR] {message}")


# get_week_number, get_week_date_range는 news_engine에서 임포트


# ===== 세션 상태 초기화 =====
def init_session_state():
    """
    세션 상태 중앙 관리
    모든 세션 상태를 한 곳에서 초기화
    """
    # 기본 상태
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.news_tab = 'collect'
        st.session_state.report_tab = 'daily'
        st.session_state.settings_tab = 'api'
    
    # 작업 결과 상태
    if 'step_results' not in st.session_state:
        st.session_state.step_results = {
            'news_items': [],
            'selected_news': [],
            'analyzed_results': [],
            'doc_url': None,
            'report_title': None
        }
    
    # 진행 상태
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    # 에러 상태
    if 'last_error' not in st.session_state:
        st.session_state.last_error = None
    
    # 통계 캐시
    if 'stats_cache' not in st.session_state:
        st.session_state.stats_cache = {
            'last_update': None,
            'data': None
        }


# ✅ 세션 상태 초기화 호출
init_session_state()


# ===== CSS 스타일 (Premium UI/UX 개편) =====
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Pretendard:wght@400;600;700&display=swap');

    :root {
        --primary-gradient: linear-gradient(135deg, #1a2a6c 0%, #b21f1f 50%, #fdbb2d 100%);
        --tta-blue: #005aab;
        --tta-gold: #c5a059;
        --glass-bg: rgba(255, 255, 255, 0.7);
        --glass-border: rgba(255, 255, 255, 0.3);
    }

    * {
        font-family: 'Pretendard', 'Inter', sans-serif !important;
    }

    /* 사이드바 및 레이아웃 배치 최적화 (풀스크린 활용도 제고) */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        max-width: 100% !important;
    }

    /* 메인 컨테이너 배경 및 텍스트 */
    .main {
        background-color: #f8f9fa;
    }

    /* 헤더 스타일링 */
    .main-header {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #005aab, #c5a059);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 2rem 0;
        letter-spacing: -0.05rem;
    }

    /* 통계 카드 (글래스모피즘) */
    .stat-card {
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.5);
        padding: 1.5rem;
        border-radius: 20px;
        text-align: center;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .stat-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.12);
        border: 1px solid #005aab;
    }
    
    .stat-number {
        font-size: 2.8rem;
        font-weight: 800;
        color: #1e293b;
        margin-bottom: 0.2rem;
    }
    
    .stat-label {
        font-size: 0.95rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05rem;
    }
    
    /* 뉴스 카드 리스트 스타일 */
    .news-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        transition: all 0.2s ease-in-out;
    }
    
    .news-card:hover {
        border-color: #005aab;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        transform: scale(1.01);
    }

    /* 정보 안내 카드 */
    .info-card {
        background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
        border-left: 6px solid #005aab;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
    
    .info-card-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
    }
    
    .info-card-content {
        color: #334155;
        font-size: 1rem;
        line-height: 1.7;
    }

    /* 사이드바 스타일링 */
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
        color: white;
    }
    
    section[data-testid="stSidebar"] .stMarkdown h1, 
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: white !important;
    }

    /* 버튼 스타일 조정 */
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s;
    }

    /* 탭 디자인 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f1f5f9;
        border-radius: 10px 10px 0 0;
        padding: 10px 20px;
        color: #64748b;
    }

    .stTabs [aria-selected="true"] {
        background-color: #005aab !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)


# ===== 설정 파일 관리 =====
CONFIG_FILE = Path("data/config.json")


def load_config():
    """설정 로드"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'ai_model': 'openai',
        'openai_api_key': OPENAI_API_KEY,
        'claude_api_key': '',
        'gemini_api_key': '',
        'perplexity_api_key': '',
        'naver_client_id': NAVER_CLIENT_ID,
        'naver_client_secret': NAVER_CLIENT_SECRET,
        'gmail_sender': SENDER_EMAIL,
        'gmail_password': GMAIL_PASSWORD,
        'gmail_receivers': RECEIVER_EMAIL,
        'google_alerts_rss': GOOGLE_ALERTS_RSS_URLS,
        'naver_queries': NAVER_QUERIES,
        'schedule_daily': '09:00',
        'schedule_weekly': 'Monday 09:00',
        'schedule_monthly': '1 09:00'
    }


def save_config(cfg):
    """설정 저장"""
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    # 설정 변경 시 AI 클라이언트 캐시 초기화 (API 키 변경 반영)
    clear_clients_cache()




# ===== 사이드바 =====
with st.sidebar:
    st.markdown("# 🚀 IRONAGE AI")
    st.markdown("### Analytics System v5.0")
    st.markdown("---")

    # 로그인 사용자 정보
    st.markdown(f"**{_user_name}**")
    st.caption(_user_email)
    if _auth_enabled:
        if st.button("로그아웃", use_container_width=True, key="sidebar_logout"):
            st.logout()
    st.markdown("---")

    selected = option_menu(
        menu_title="메뉴",
        options=["대시보드", "뉴스 관리", "리포트", "뉴스 검색", "이슈 추적", "내 설정", "설정"],
        icons=["speedometer2", "newspaper", "file-earmark-text", "search", "graph-up", "person-gear", "gear"],
        menu_icon="cast",
        default_index=0,
    )

    st.markdown("---")
    st.markdown("**한국정보통신기술협회(TTA)**")
    st.markdown("표준화본부 이동통신표준팀")
    st.markdown(f"*{datetime.now().strftime('%Y-%m-%d %H:%M')}*")


# ===== 1. 대시보드 페이지 =====
if selected == "대시보드":
    st.markdown('<h1 class="main-header">📊 뉴스 인텔리전스 모니터링 대시보드</h1>', unsafe_allow_html=True)
    
    # 통계 카드
    stats = get_db_statistics()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total']}</div>
            <div class="stat-label">전체 뉴스</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['analyzed']}</div>
            <div class="stat-label">분석 완료</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['today']}</div>
            <div class="stat-label">오늘 수집</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['pending']}</div>
            <div class="stat-label">대기 중</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ===== ✅ 전체 프로세스 실행 (자동 엑셀 생성 포함) =====
    st.markdown("### 🚀 전체 프로세스 실행")
    
    info_html = """
    <div class="info-card">
        <div class="info-card-title">📋 실행 내용</div>
        <div class="info-card-content">
            <strong>1단계:</strong> 뉴스 수집 (Google Alerts + Naver) → DB 저장<br>
            <strong>2단계:</strong> AI 뉴스 선별 (중요도 평가)<br>
            <strong>3단계:</strong> 심층 분석 (본문 수집 + AI 분석 + 키워드 추출)<br>
            <strong>4단계:</strong> 구글 문서 생성<br>
            <strong>5단계:</strong> 이메일 자동 발송<br>
            <strong>6단계:</strong> 주간 누적 엑셀 자동 저장 ✨<br>
            <strong>7단계:</strong> 키워드 통계 엑셀 자동 저장 ✨<br>
            <br>
            <strong>⏱️ 예상 소요 시간:</strong> 30분 이내<br>
            <strong>💾 엑셀 파일:</strong> data/reports 폴더에 자동 저장
        </div>
    </div>
    """
    st.markdown(info_html, unsafe_allow_html=True)
    
    # 분석 개수 선택
    num_analyze = st.slider("📊 분석할 뉴스 개수", 5, 20, 10, key="full_process_slider")
    
    # 전체 프로세스 시작 버튼
    if st.button("🚀 전체 프로세스 시작", type="primary", use_container_width=True, key="full_process_start"):
        progress_bar = st.progress(0)
        status_text = st.empty()
    
        try:
            # ✅ 현재 선택된 AI 모델 가져오기
            cfg = load_config()
            current_ai_model = cfg.get('ai_model', 'openai')
        
            st.info(f"🤖 사용 AI 모델: **{current_ai_model.upper()}**")
        
            # 1단계: 수집
            status_text.markdown("### 📡 1/7: 뉴스 수집 중...")
            progress_bar.progress(0.1)
        
            news_items = get_news_data()
            saved_count = save_news_to_db(news_items)
        
            st.success(f"✅ 1단계: {len(news_items)}개 수집, {saved_count}개 저장")
            progress_bar.progress(0.15)
        
            # 2단계: 선별 (60개로 수정)
            status_text.markdown("### 🤖 2/7: AI 선별 중...")
            progress_bar.progress(0.2)
        
            # ✅ 수정: 선별 개수를 60개로 증가
            selected_news = filter_news_by_ai(news_items, ai_model=current_ai_model, max_results=50)

            st.success(f"✅ 2단계: {len(selected_news)}개 선별 (최대 50개)")
            progress_bar.progress(0.3)
        
            # 3단계: 분석
            status_text.markdown("### 📝 3/7: 심층 분석 중...")
            progress_bar.progress(0.35)
        
            _replacement_pool = selected_news[num_analyze:] + [
                item for item in news_items
                if item['link'] not in {n['link'] for n in selected_news}
            ]

            def _on_analysis_progress(done, total):
                progress_bar.progress(0.35 + 0.25 * (done / total))
                status_text.markdown(f"### 📝 3/7: 심층 분석 중... ({done}/{total})")

            analyzed_results = analyze_news_with_replacement(
                selected_news[:num_analyze],
                _replacement_pool,
                target_count=num_analyze,
                ai_model=current_ai_model,
                progress_callback=_on_analysis_progress,
            )
        
            st.success(f"✅ 3단계: {len(analyzed_results)}개 분석")
            progress_bar.progress(0.6)
        
            # 4단계: 문서 생성
            status_text.markdown("### 📄 4/7: 구글 문서 생성 중...")
            progress_bar.progress(0.65)
        
            doc_url, report_title = generate_google_doc_report(analyzed_results)
        
            if doc_url:
                st.success("✅ 4단계: 문서 생성 완료")
                st.markdown(f"[📄 구글 문서 보기]({doc_url})")
        
            progress_bar.progress(0.75)
        
            # 5단계: 이메일 (수정 버전)
            status_text.markdown("### 📧 5/7: 이메일 발송 중...")
        
            # ✅ 수정: 선별된 60개 중 미분석 뉴스를 "추가 수집 뉴스"로 사용
            analyzed_links = {r['link'] for r in analyzed_results}
            remaining_selected_news = [n for n in selected_news if n['link'] not in analyzed_links]
        
            send_gmail_report(report_title, analyzed_results, doc_url, remaining_selected_news)
        
            st.success("✅ 5단계: 이메일 발송 완료")
            st.info(f"📧 추가 수집 뉴스: {len(remaining_selected_news)}개 (선별된 60개 중 미분석)")
            progress_bar.progress(0.85)
        
            # ✅ 6단계: 주간 누적 엑셀 자동 저장
            status_text.markdown("### 📊 6/7: 주간 누적 엑셀 자동 저장 중...")
            progress_bar.progress(0.9)
        
            excel_path = save_analysis_to_weekly_excel(analyzed_results)
        
            if excel_path:
                year, week, week_str = get_week_number()
                st.success(f"✅ 6단계: 주간 엑셀 누적 저장 완료 ({week_str})")
                st.info(f"📂 저장 위치: {excel_path}")
                
                # 중복도 검증
                try:
                    from news_engine import verify_deduplication
                    duplication_rate = verify_deduplication(analyzed_results)
        
                    st.info(f"""
                    📊 **품질 지표:**
                    - AI 선별: {len(selected_news)}개 (중복 제거 완료)
                    - 심층 분석: {len(analyzed_results)}개
                    - 중복도: {duplication_rate:.1%} (낮을수록 좋음)
        
                    💡 **Tip:** 중복도가 30% 이상이면 프롬프트 개선이 필요합니다.
                    """)
                except Exception as e:
                    st.warning(f"⚠️ 중복도 검증 실패: {e}")
                
                
            else:
                st.warning("⚠️ 6단계: 엑셀 저장 실패")
        
            progress_bar.progress(0.95)
        
            # ✅ 7단계: 키워드 통계 누적 저장
            status_text.markdown("### 📈 7/7: 키워드 통계 누적 저장 중...")
        
            keyword_path = save_keyword_summary_to_weekly_excel()
        
            if keyword_path:
                st.success(f"✅ 7단계: 키워드 통계 누적 저장 완료")
                st.info(f"📂 저장 위치: {keyword_path}")
            else:
                st.warning("⚠️ 7단계: 키워드 통계 저장 실패")
        
            progress_bar.progress(1.0)
        
            # ✅ 최종 안내 메시지
            status_text.markdown("### ✅ 전체 프로세스 완료!")
        
            st.success("🎉 모든 작업이 완료되었습니다!")
            st.info(f"""
            📁 **생성된 파일 확인:**
            - 주간 누적 엑셀: `data/reports/news_analysis_{week_str}.xlsx` (누적)
            - 키워드 통계: `data/reports/keyword_summary_{week_str}.xlsx` (누적)
        
            📊 **이번 실행 결과:**
            - AI 선별: {len(selected_news)}개 (최대 60개)
            - 심층 분석: {len(analyzed_results)}개
            - 추가 수집 뉴스: {len(remaining_selected_news)}개 (이메일 발송)
        
            💡 **파일 다운로드:**
            '뉴스 관리' → '주차별 보고서' 탭에서 확인하세요.
            """)
        
            st.balloons()
    
        except Exception as e:
            st.error(f"❌ 오류: {str(e)}")
            st.error(traceback.format_exc())
    
    # ===== 🤖 AI 모델 선택 및 빠른 실행 =====
    st.markdown("---")
    st.markdown("### 🤖 AI 모델 설정 및 빠른 실행")
    
    cfg = load_config()
    
    # ✅ 3열 레이아웃 생성
    col_model, col_status, col_quick = st.columns([2, 1, 1])
    
    with col_model:
        ai_model = st.selectbox(
            "분석에 사용할 AI 모델",
            options=['openai', 'claude', 'perplexity', 'gemini'],
            index=['openai', 'claude', 'perplexity', 'gemini'].index(cfg.get('ai_model', 'openai')),
            format_func=lambda x: {
                'openai': '🟢 OpenAI (GPT-4o)',
                'claude': '🟣 Anthropic (Claude Sonnet 4)',
                'perplexity': '🟠 Perplexity (Sonar Pro)',
                'gemini': '🔵 Google (Gemini 2.5 Flash)'
            }[x],
            key="ai_model_selector",
            help="뉴스 분석에 사용할 AI 모델을 선택하세요."
        )
        
        # FIX: st.rerun() 무한 루프 방지 - 이미 저장된 모델과 다를 때만 저장 후 1회 rerun
        if ai_model != cfg.get('ai_model'):
            cfg['ai_model'] = ai_model
            save_config(cfg)
            # session_state 플래그로 중복 rerun 방지
            if not st.session_state.get('_model_rerun_guard'):
                st.session_state['_model_rerun_guard'] = True
                st.success(f"✅ AI 모델이 **{ai_model.upper()}**로 변경되었습니다!")
                st.rerun()
        else:
            # 모델이 동일하면 가드 초기화
            st.session_state.pop('_model_rerun_guard', None)
    
    with col_status:
        st.markdown("**📊 모델 상태**")
        
        # API 키 확인
        api_key_status = {
            'openai': bool(cfg.get('openai_api_key', '')) and not cfg.get('openai_api_key', '').startswith('YOUR_'),
            'claude': bool(cfg.get('claude_api_key', '')) and not cfg.get('claude_api_key', '').startswith('YOUR_'),
            'perplexity': bool(cfg.get('perplexity_api_key', '')) and not cfg.get('perplexity_api_key', '').startswith('YOUR_'),
            'gemini': bool(cfg.get('gemini_api_key', '')) and not cfg.get('gemini_api_key', '').startswith('YOUR_')
        }
        
        # 선택된 모델의 상태 표시
        if api_key_status[ai_model]:
            st.success("✅ API 키 설정됨")
        else:
            st.error("❌ API 키 미설정")
            st.caption("💡 설정 탭에서 API 키를 입력하세요.")
    
    with col_quick:
        st.markdown("**⚡ 빠른 실행**")
        if st.button("🔄 지금 뉴스 수집", key="quick_collect", use_container_width=True):
            with st.spinner(f"뉴스 수집 중... (모델: {ai_model.upper()})"):
                try:
                    # ✅ 선택된 AI 모델 전달
                    run_daily_collection(ai_model=ai_model)
                    st.success(f"✅ 뉴스 수집 완료! (사용 모델: {ai_model.upper()})")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 오류: {str(e)}")
    
    # 모델별 특징 안내
    with st.expander("📖 AI 모델 선택 가이드"):
        st.markdown("""
        ### 🤖 각 모델의 특징
        
        #### 🟢 OpenAI (GPT-4o)
        - **장점:** 가장 안정적이고 검증된 성능
        - **추천:** 일반적인 뉴스 분석, 정확한 요약 필요 시
        - **비용:** 중간 수준
        
        #### 🟣 Anthropic (Claude Sonnet 4)
        - **장점:** 긴 문맥 이해, 세밀한 분석
        - **추천:** 복잡한 정책 분석, 심층 리포트
        - **비용:** 중간~높음
        
        #### 🟠 Perplexity (Sonar Pro)
        - **장점:** 최신 정보 반영, 빠른 응답
        - **추천:** 실시간 트렌드 분석, 속보성 뉴스
        - **비용:** 낮음~중간
        
        #### 🔵 Google (Gemini 2.5 Flash)
        - **장점:** 빠른 처리 속도, 비용 효율
        - **추천:** 대량 뉴스 처리, 빠른 스캔
        - **비용:** 낮음
        
        ---
        
        💡 **Tip:** 일일 분석은 GPT-4o, 주간 리포트는 Claude를 추천합니다.
        """)
    
    # ===== 키워드 트렌드 (데이터 시각화 대시보드) =====
    st.markdown("---")
    st.markdown("### 📈 데이터 시각화 대시보드")
    
    # ✅ 추가: 새로고침 버튼
    col_refresh, col_period = st.columns([1, 3])
    
    with col_refresh:
        if st.button("🔄 데이터 새로고침", key="refresh_dashboard", use_container_width=True):
            st.rerun()
    
    with col_period:
        dashboard_days = st.selectbox(
            "분석 기간",
            options=[7, 14, 30, 90],
            index=0,
            format_func=lambda x: f"최근 {x}일",
            key="dashboard_period"
        )
    
    # ✅ 개선: 실시간 데이터 로드
    dashboard_news = load_news_from_db(days=dashboard_days)
    
    if dashboard_news and len(dashboard_news) > 0:
        # ===== ✅ 추가: 주요 조치 사항 요약 =====
        critical_high_news = [
            n for n in dashboard_news 
            if n.get('is_analyzed') and _get_impact_info(n)['impact_level'] in ('Critical', 'High')
        ]
        
        if critical_high_news:
            sorted_urgent = sorted(
                critical_high_news, 
                key=lambda x: IMPACT_LEVEL_ORDER.get(_get_impact_info(x)['impact_level'], 2)
            )
            
            st.markdown("### 🚨 주요 조치 필요 항목 (Critical / High)")
            st.markdown("""<div style="background-color: #fff1f2; padding: 15px; border-radius: 12px; border-left: 6px solid #dc2626; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">""", unsafe_allow_html=True)
            for urgent in sorted_urgent[:5]: # 최대 5개 노출
                impact = _get_impact_info(urgent)
                level = impact['impact_level']
                icon = "🚨" if level == 'Critical' else "⚠️"
                color = "#dc2626" if level == 'Critical' else "#ea580c"
                
                st.markdown(f"**{icon} <span style='color: {color};'>[{level}]</span> [{urgent['source']}] {urgent['title']}**", unsafe_allow_html=True)
                if impact['tta_action_item']:
                    st.markdown(f"<p style='margin-left: 32px; margin-top: 4px; margin-bottom: 12px; font-size: 14.5px; font-weight: 600; color: #334155;'>▶ TTA 조치: {impact['tta_action_item']}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # 4열 레이아웃으로 변경
        viz_col1, viz_col2, viz_col3, viz_col4 = st.columns(4)
        
        # === 차트 1: 일별 뉴스 수집 추이 ===
        with viz_col1:
            st.markdown("#### 📊 일별 수집 추이")
            try:
                daily_counts = defaultdict(int)
        
                for news in dashboard_news:
                    # ✅ 수정: collected_at (실제 수집 일자) 우선 사용
                    date_str = news.get('collected_at', '') or news.get('published', '')
            
                    if date_str:
                        try:
                            # 여러 날짜 형식 지원
                            if isinstance(date_str, str):
                                if 'T' in date_str:  # ISO 형식
                                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                else:
                                    date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                            else:
                                date_obj = date_str
                    
                            day_key = date_obj.strftime('%m-%d')
                            daily_counts[day_key] += 1
                        except Exception:
                            continue
        
                if daily_counts:
                    df_daily = pd.DataFrame(
                        sorted(daily_counts.items()),
                        columns=['날짜', '기사 수']
                    )
            
                    fig_daily = px.line(
                        df_daily,
                        x='날짜',
                        y='기사 수',
                        markers=True,
                        title="",
                        color_discrete_sequence=['#667eea']
                    )
                    fig_daily.update_layout(
                        height=250,
                        margin=dict(l=0, r=0, t=0, b=0),
                        showlegend=False,
                        xaxis_title="수집 일자",
                        yaxis_title="기사 수"
                    )
                    fig_daily.update_traces(line_width=3, marker_size=8)
                    st.plotly_chart(fig_daily, use_container_width=True)
            
                    total_articles = sum(daily_counts.values())
                    avg_daily = total_articles / len(daily_counts)
                    st.caption(f"평균 일일 수집: {avg_daily:.1f}개 (수집 일자 기준)")
                else:
                    st.info("일별 데이터 부족")
            except Exception as e:
                st.error(f"차트 생성 오류: {str(e)}")
        
        # === 차트 2: 출처별 분포 ===
        with viz_col2:
            st.markdown("#### 📰 출처별 분포")
            try:
                sources = [n['source'] for n in dashboard_news if n.get('source')]
                source_counts = Counter(sources)
                
                if source_counts:
                    df_source = pd.DataFrame(
                        source_counts.most_common(8),
                        columns=['출처', '기사 수']
                    )
                    
                    fig_pie = px.pie(
                        df_source,
                        values='기사 수',
                        names='출처',
                        title="",
                        color_discrete_sequence=px.colors.sequential.RdBu,
                        hole=0.3
                    )
                    fig_pie.update_layout(
                        height=250,
                        margin=dict(l=0, r=0, t=0, b=0),
                        showlegend=True,
                        legend=dict(
                            orientation="v",
                            yanchor="middle",
                            y=0.5,
                            xanchor="left",
                            x=1.05,
                            font=dict(size=9)
                        )
                    )
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                    top_sources = source_counts.most_common(3)
                    st.caption(f"Top 3: {', '.join([f'{s}({c})' for s, c in top_sources])}")
                else:
                    st.info("출처 데이터 부족")
            except Exception as e:
                st.error(f"차트 생성 오류: {str(e)}")
        
        # === 차트 3: 분석 진행률 ===
        with viz_col3:
            st.markdown("#### ✅ 분석 진행률")
            try:
                total = len(dashboard_news)
                analyzed = len([n for n in dashboard_news if n.get('is_analyzed')])
                progress_rate = (analyzed / total * 100) if total > 0 else 0
                
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=progress_rate,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': ""},
                    delta={'reference': 80, 'increasing': {'color': "green"}},
                    gauge={
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "#667eea"},
                        'steps': [
                            {'range': [0, 50], 'color': "#ffe5e5"},
                            {'range': [50, 80], 'color': "#fff8e1"},
                            {'range': [80, 100], 'color': "#e8f5e9"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 90
                        }
                    }
                ))
                fig_gauge.update_layout(
                    height=250,
                    margin=dict(l=20, r=20, t=30, b=0)
                )
                st.plotly_chart(fig_gauge, use_container_width=True)
                
                st.metric(
                    "분석 완료",
                    f"{analyzed}개",
                    f"{total - analyzed}개 대기중",
                    delta_color="normal"
                )
                
                st.progress(progress_rate / 100)
            
            except Exception as e:
                st.error(f"게이지 생성 오류: {str(e)}")
        
        # === 차트 4: 영향도 분포 ===
        with viz_col4:
            st.markdown("#### 🎯 영향도 분포")
            try:
                analyzed_news = [n for n in dashboard_news if n.get('is_analyzed')]
                impacts = [_get_impact_info(n)['impact_level'] for n in analyzed_news]
                impact_counts = Counter(impacts)
                
                if impact_counts:
                    df_impact = pd.DataFrame(
                        list(impact_counts.items()),
                        columns=['영향도', '기사 수']
                    )
                    
                    df_impact['정렬'] = df_impact['영향도'].map(lambda x: IMPACT_LEVEL_ORDER.get(x, 99))
                    df_impact = df_impact.sort_values('정렬')
                    
                    color_discrete_map = {
                        k: f"rgb({int(v['red']*255)},{int(v['green']*255)},{int(v['blue']*255)})"
                        for k, v in IMPACT_LEVEL_COLOR_RGB.items()
                    }
                    
                    fig_impact = px.pie(
                        df_impact,
                        values='기사 수',
                        names='영향도',
                        title="",
                        color='영향도',
                        color_discrete_map=color_discrete_map,
                        hole=0.4
                    )
                    fig_impact.update_layout(
                        height=250,
                        margin=dict(l=0, r=0, t=0, b=0),
                        showlegend=True,
                        legend=dict(
                            orientation="v",
                            yanchor="middle",
                            y=0.5,
                            xanchor="left",
                            x=1.05,
                            font=dict(size=9)
                        )
                    )
                    fig_impact.update_traces(textposition='inside', textinfo='percent')
                    st.plotly_chart(fig_impact, use_container_width=True)
                else:
                    st.info("영향도 데이터 부족")
            except Exception as e:
                st.error(f"차트 생성 오류: {str(e)}")

        # ===== 🔥 AI 기반 키워드 분석 =====
        st.markdown("---")
        st.markdown("#### 🤖 AI 추출 핵심 키워드 분석")
        
        col_refresh2, col_period2 = st.columns([1, 3])
        
        with col_refresh2:
            if st.button("🔄 키워드 새로고침", key="refresh_keywords", use_container_width=True):
                st.rerun()
        
        with col_period2:
            keyword_days = st.selectbox(
                "분석 기간",
                options=[7, 14, 30, 90],
                index=2,
                format_func=lambda x: f"최근 {x}일",
                key="keyword_period"
            )

        try:
            # Bug 6: is_analyzed 플래그 대신 extracted_keywords 존재 여부로 필터링
            _all_news = load_news_from_db(days=keyword_days)
            news_with_keywords = [n for n in _all_news if n.get('extracted_keywords')]
            dashboard_news_analyzed = news_with_keywords

            st.info(f"📊 분석 대상: 최근 {keyword_days}일간 키워드 추출된 뉴스 {len(news_with_keywords)}개")
            
            if not news_with_keywords:
                st.warning(f"⚠️ 최근 {keyword_days}일간 키워드가 추출된 뉴스가 없습니다.")
                st.info("💡 뉴스를 먼저 분석하거나 기간을 늘려보세요.")
            else:
                st.success(f"✅ {len(news_with_keywords)}개 뉴스에서 키워드 발견!")
            
            all_keywords = []
            keyword_categories = Counter()
            importance_counts = Counter()
            
            all_companies = []
            all_technologies = []
            all_countries = []
            
            # 기술명 동의어/세부항목 통합 딕셔너리
            TECH_SYNONYMS = {
                "저궤도 위성통신": "위성통신", "저궤도": "위성통신", "satellite communications": "위성통신", "위성 통신": "위성통신",
                "생성형 ai": "AI", "genai": "AI", "인공지능": "AI", "생성형ai": "AI", "인공 지능": "AI",
                "6세대 이동통신": "6G", "sixth generation": "6G", "6세대 통신": "6G",
                "개방형 무선 접속망": "Open RAN", "오픈랜": "Open RAN", "oran": "Open RAN", "openran": "Open RAN",
                "사물인터넷": "IoT", "비지상 네트워크": "NTN", "비지상네트워크": "NTN"
            }
            
            for news in news_with_keywords:
                if news.get('extracted_keywords'):
                    try:
                        keyword_data = json.loads(news['extracted_keywords'])
                        keywords = keyword_data.get('keywords', [])
                        
                        for kw in keywords:
                            term = kw.get('term', '')
                            category = kw.get('category', '기타')
                            importance = kw.get('importance', 'medium')
                            
                            if term:
                                all_keywords.append({
                                    'term': term,
                                    'category': category,
                                    'importance': importance
                                })
                                keyword_categories[category] += 1
                                importance_counts[importance] += 1
                                
                        # 엔티티 추출 (구 버전 데이터에는 없을 수 있으므로 .get(키, []) 사용)
                        rel_companies = keyword_data.get('related_companies', [])
                        key_techs = keyword_data.get('key_technologies', [])
                        tgt_countries = keyword_data.get('target_countries', [])
                        
                        if isinstance(rel_companies, list):
                            all_companies.extend([c for c in rel_companies if c])
                            
                        if isinstance(key_techs, list):
                            for tech in key_techs:
                                if not tech: continue
                                # 기술 통합 규칙 적용 (소문자 변환 후 매핑)
                                norm_tech = TECH_SYNONYMS.get(tech.lower(), tech)
                                all_technologies.append(norm_tech)
                                
                        if isinstance(tgt_countries, list):
                            all_countries.extend([c for c in tgt_countries if c])
                            
                    except Exception:
                        continue
            
            if all_keywords:
                keyword_freq = Counter([kw['term'] for kw in all_keywords])
                top_keywords = keyword_freq.most_common(30)
                
                col_kw1, col_kw2 = st.columns(2)
                
                with col_kw1:
                    st.markdown("**📊 TOP 20 키워드**")
                    
                    df_keywords = pd.DataFrame(top_keywords[:20], columns=['키워드', '빈도'])
                    
                    fig_keywords = px.bar(
                        df_keywords,
                        x='빈도',
                        y='키워드',
                        orientation='h',
                        title="",
                        color='빈도',
                        color_continuous_scale='Viridis',
                        text='빈도'
                    )
                    fig_keywords.update_layout(
                        height=500,
                        yaxis={'categoryorder': 'total ascending'},
                        showlegend=False
                    )
                    fig_keywords.update_traces(textposition='outside')
                    
                    st.plotly_chart(fig_keywords, use_container_width=True)
                
                with col_kw2:
                    st.markdown("**📂 카테고리별 분포**")
                    
                    df_categories = pd.DataFrame(
                        keyword_categories.most_common(),
                        columns=['카테고리', '개수']
                    )
                    
                    fig_categories = px.pie(
                        df_categories,
                        values='개수',
                        names='카테고리',
                        title="",
                        color_discrete_sequence=px.colors.qualitative.Set3,
                        hole=0.4
                    )
                    fig_categories.update_layout(height=500)
                    fig_categories.update_traces(textposition='inside', textinfo='percent+label')
                    
                    st.plotly_chart(fig_categories, use_container_width=True)
                
                st.markdown("**⭐ 키워드 중요도 분포**")
                
                col_imp1, col_imp2, col_imp3 = st.columns(3)
                
                total_kw = sum(importance_counts.values())
                
                with col_imp1:
                    high_ratio = (importance_counts['high'] / total_kw * 100) if total_kw > 0 else 0
                    st.metric("High 중요도", f"{importance_counts['high']}개", f"{high_ratio:.1f}%")
                
                with col_imp2:
                    medium_ratio = (importance_counts['medium'] / total_kw * 100) if total_kw > 0 else 0
                    st.metric("Medium 중요도", f"{importance_counts['medium']}개", f"{medium_ratio:.1f}%")
                
                with col_imp3:
                    low_ratio = (importance_counts['low'] / total_kw * 100) if total_kw > 0 else 0
                    st.metric("Low 중요도", f"{importance_counts['low']}개", f"{low_ratio:.1f}%")
                
                st.markdown("---")
                st.markdown("**🏷️ 키워드 태그 (중요도별)**")
                
                high_keywords = [kw['term'] for kw in all_keywords if kw['importance'] == 'high']
                medium_keywords = [kw['term'] for kw in all_keywords if kw['importance'] == 'medium']
                
                if high_keywords:
                    st.markdown("**🔴 High 중요도**")
                    high_freq = Counter(high_keywords).most_common(15)
                    tags_html = " ".join([
                        f'<span style="display:inline-block; background: linear-gradient(135deg, #ef4444 0%, #991b1b 100%); color:white; '
                        f'padding:6px 14px; margin:4px; border-radius:20px; font-size:13px; font-weight:600; '
                        f'box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2); word-wrap:break-word; overflow:hidden; max-width:200px;">'
                        f'🔥 {term[:15] + "…" if len(term) > 15 else term} <span style="opacity:0.8; font-weight:400; margin-left:4px;">{count}</span></span>'
                        for term, count in high_freq
                    ])
                    st.markdown(tags_html, unsafe_allow_html=True)

                if medium_keywords:
                    st.markdown("**🟡 Medium 중요도**")
                    medium_freq = Counter(medium_keywords).most_common(15)
                    tags_html = " ".join([
                        f'<span style="display:inline-block; background: linear-gradient(135deg, #f59e0b 0%, #b45309 100%); color:white; '
                        f'padding:6px 14px; margin:4px; border-radius:20px; font-size:13px; font-weight:600; '
                        f'box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2); word-wrap:break-word; overflow:hidden; max-width:200px;">'
                        f'✨ {term[:15] + "…" if len(term) > 15 else term} <span style="opacity:0.8; font-weight:400; margin-left:4px;">{count}</span></span>'
                        for term, count in medium_freq
                    ])
                    st.markdown(tags_html, unsafe_allow_html=True)
                
                with st.expander("📋 전체 키워드 목록 (복사용)"):
                    keyword_list = ", ".join([kw for kw, _ in top_keywords])
                    st.text_area(
                        "키워드 목록 (Ctrl+A → Ctrl+C로 복사)",
                        value=keyword_list,
                        height=100,
                        key="ai_keyword_copy"
                    )
                
                # ===== 🗺️ 인텔리전스 매트릭스 (다차원 엔티티 뷰) =====
                st.markdown("---")
                st.markdown("#### 🧭 인텔리전스 매트릭스 (심층 엔티티 분석)")

                if all_companies or all_technologies or all_countries:
                    # ── 1. Top 5 요약 테이블 (기존 유지) ──────────────────────
                    em_col1, em_col2, em_col3 = st.columns(3)

                    with em_col1:
                        st.markdown("**🏢 핫 모멘텀 기업 Top 5**")
                        if all_companies:
                            comp_top = Counter(all_companies).most_common(5)
                            comp_df = pd.DataFrame(comp_top, columns=['기업 (Company)', '등장 빈도'])
                            st.dataframe(comp_df, hide_index=True, use_container_width=True)
                        else:
                            st.info("데이터 없음")

                    with em_col2:
                        st.markdown("**🛠️ 부상하는 핵심기술 Top 5**")
                        if all_technologies:
                            tech_top = Counter(all_technologies).most_common(5)
                            tech_df = pd.DataFrame(tech_top, columns=['기술 (Tech/Standard)', '등장 빈도'])
                            st.dataframe(tech_df, hide_index=True, use_container_width=True)
                        else:
                            st.info("데이터 없음")

                    with em_col3:
                        st.markdown("**🌍 정책/규제 활성 국가 Top 5**")
                        if all_countries:
                            country_top = Counter(all_countries).most_common(5)
                            country_df = pd.DataFrame(country_top, columns=['국가 (Country)', '등장 빈도'])
                            st.dataframe(country_df, hide_index=True, use_container_width=True)
                        else:
                            st.info("데이터 없음")

                    # ── 2. 공출현 히트맵 + 지식 그래프 ───────────────────────
                    try:
                        from knowledge_graph import (
                            build_entity_graph,
                            render_graph_html,
                            get_co_occurrence_matrix,
                            detect_surge_entities,
                            get_graph_stats,
                        )
                        _KG_AVAILABLE = True
                    except ImportError:
                        _KG_AVAILABLE = False

                    if _KG_AVAILABLE:
                        st.markdown("---")

                        _kg_tab1, _kg_tab2, _kg_tab3, _kg_tab4 = st.tabs([
                            "🔥 급등 알림",
                            "🔲 공출현 히트맵",
                            "🕸️ 지식 그래프",
                            "📊 주간 키워드 비교",
                        ])

                        # ── 탭 1: 급등 알림 ──────────────────────────────────
                        with _kg_tab1:
                            _prev_days = keyword_days * 2
                            _news_prev_raw = load_news_from_db(days=_prev_days, is_analyzed=True)
                            _news_prev = [n for n in _news_prev_raw if n.get('extracted_keywords')]
                            # 현재 기간 = 최근 keyword_days, 이전 기간 = 그 이전 keyword_days
                            import datetime as _dt
                            _cutoff = _dt.datetime.now() - _dt.timedelta(days=keyword_days)
                            _news_prev_only = [
                                n for n in _news_prev
                                if n.get('collected_at') and str(n['collected_at']) < str(_cutoff)
                            ]

                            _surges = detect_surge_entities(
                                news_current=news_with_keywords,
                                news_prev=_news_prev_only,
                                tech_synonyms=TECH_SYNONYMS,
                                threshold=0.5,
                                min_current=2,
                            )

                            if _surges:
                                _type_icon = {'company': '🏢', 'tech': '🛠️', 'country': '🌍'}
                                for s in _surges[:8]:
                                    _icon = _type_icon.get(s['node_type'], '📌')
                                    _pct = s['pct_change']
                                    _pct_str = f"+{_pct*100:.0f}%" if _pct != float('inf') else "신규 등장"
                                    _color = "#ef4444" if _pct >= 1.0 else "#f59e0b"
                                    st.markdown(
                                        f'<div style="display:flex;align-items:center;gap:12px;'
                                        f'padding:10px 16px;margin:6px 0;border-radius:8px;'
                                        f'background:rgba(255,255,255,0.04);border-left:4px solid {_color};">'
                                        f'<span style="font-size:1.2em">{_icon}</span>'
                                        f'<span style="font-weight:600;flex:1">{s["name"]}</span>'
                                        f'<span style="color:{_color};font-weight:700;font-size:1.1em">{_pct_str}</span>'
                                        f'<span style="color:#888;font-size:0.85em">'
                                        f'{s["prev_count"]}→{s["curr_count"]}회</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                            else:
                                st.info("이전 기간 대비 급등한 엔티티가 없습니다. 분석된 기사가 충분히 누적되면 표시됩니다.")

                        # ── 탭 2: 공출현 히트맵 ──────────────────────────────
                        with _kg_tab2:
                            _heatmap_n = st.slider(
                                "표시할 상위 N개 (기업·기술 각각)",
                                min_value=3, max_value=12, value=7, step=1,
                                key="heatmap_n_slider",
                            )
                            _co_matrix = get_co_occurrence_matrix(
                                news_with_keywords,
                                tech_synonyms=TECH_SYNONYMS,
                                top_companies=_heatmap_n,
                                top_techs=_heatmap_n,
                            )

                            if not _co_matrix.empty and _co_matrix.values.sum() > 0:
                                import plotly.express as px
                                _fig_heat = px.imshow(
                                    _co_matrix,
                                    labels=dict(x="기술 (Technology)", y="기업 (Company)", color="공출현 횟수"),
                                    color_continuous_scale="Blues",
                                    aspect="auto",
                                    text_auto=True,
                                )
                                _fig_heat.update_layout(
                                    height=420,
                                    plot_bgcolor='rgba(0,0,0,0)',
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    font_color='#e8e8e8',
                                    coloraxis_showscale=True,
                                    margin=dict(l=20, r=20, t=20, b=20),
                                )
                                _fig_heat.update_xaxes(tickangle=-30)
                                st.plotly_chart(_fig_heat, use_container_width=True)
                                st.caption("셀 값 = 같은 기사에 함께 등장한 횟수. 색이 진할수록 연관성이 강합니다.")
                            else:
                                st.info("공출현 데이터가 부족합니다. 기업·기술이 함께 등장하는 기사가 더 필요합니다.")

                        # ── 탭 3: 지식 그래프 ────────────────────────────────
                        with _kg_tab3:
                            _graph_col1, _graph_col2 = st.columns([3, 1])

                            with _graph_col2:
                                _min_w = st.slider(
                                    "최소 공출현 횟수",
                                    min_value=1, max_value=5, value=1, step=1,
                                    key="kg_min_weight",
                                    help="이 값 이상 함께 등장한 엔티티 쌍만 연결선으로 표시합니다.",
                                )
                                st.markdown(
                                    "<div style='margin-top:12px'>"
                                    "<b>범례</b><br>"
                                    "<span style='color:#4a90e2'>●</span> 🏢 기업<br>"
                                    "<span style='color:#e74c3c'>◆</span> 🛠️ 기술<br>"
                                    "<span style='color:#2ecc71'>■</span> 🌍 국가<br>"
                                    "<small style='color:#888'>노드 크기 = 등장 빈도<br>"
                                    "선 굵기 = 공출현 횟수</small>"
                                    "</div>",
                                    unsafe_allow_html=True,
                                )

                            with _graph_col1:
                                _G = build_entity_graph(
                                    news_with_keywords,
                                    tech_synonyms=TECH_SYNONYMS,
                                    min_weight=_min_w,
                                )
                                _stats = get_graph_stats(_G)

                                if _stats:
                                    _s1, _s2, _s3 = st.columns(3)
                                    _s1.metric("노드 수", _stats['total_nodes'])
                                    _s2.metric("연결 수", _stats['total_edges'])
                                    _s3.metric("밀도", f"{_stats['density']:.3f}")

                                _graph_html = render_graph_html(_G, height=520)
                                import streamlit.components.v1 as _components
                                _components.html(_graph_html, height=540, scrolling=False)

                                if _stats.get('top_central'):
                                    with st.expander("📌 중심성 높은 엔티티 Top 5"):
                                        for _name, _score in _stats['top_central']:
                                            _ntype = _G.nodes[_name].get('node_type', '') if _G and _name in _G.nodes else ''
                                            _icon = {'company': '🏢', 'tech': '🛠️', 'country': '🌍'}.get(_ntype, '📌')
                                            st.write(f"{_icon} **{_name}** — 중심성 {_score:.3f}")

                        # ── 탭 4: 주간 키워드 비교 히트맵 ─────────────────────
                        with _kg_tab4:
                            import datetime as _wkdt
                            _wk_prev_raw = load_news_from_db(days=keyword_days * 2)
                            _wk_prev_all = [n for n in _wk_prev_raw if n.get('extracted_keywords')]
                            _wk_cutoff = _wkdt.datetime.now() - _wkdt.timedelta(days=keyword_days)
                            _wk_prev_only = [
                                n for n in _wk_prev_all
                                if n.get('collected_at') and str(n['collected_at']) < str(_wk_cutoff)
                            ]

                            def _extract_tech_freq(news_list):
                                from collections import Counter
                                _ctr = Counter()
                                for _n in news_list:
                                    try:
                                        _kw_raw = _n.get('extracted_keywords', '{}') or '{}'
                                        _kw_parsed = json.loads(_kw_raw) if isinstance(_kw_raw, str) else _kw_raw
                                        _techs = _kw_parsed.get('key_technologies', [])
                                        if isinstance(_techs, list):
                                            for _t in _techs:
                                                _k = str(_t).strip()
                                                if _k:
                                                    _ctr[TECH_SYNONYMS.get(_k.lower(), _k)] += 1
                                    except Exception:
                                        pass
                                return _ctr

                            if news_with_keywords and _wk_prev_only:
                                _curr_ctr = _extract_tech_freq(news_with_keywords)
                                _prev_ctr = _extract_tech_freq(_wk_prev_only)
                                _all_keys = list(dict.fromkeys(
                                    [k for k, _ in _curr_ctr.most_common(12)] +
                                    [k for k, _ in _prev_ctr.most_common(12)]
                                ))[:15]

                                if _all_keys:
                                    import plotly.express as px
                                    import pandas as pd
                                    _hm_df = pd.DataFrame({
                                        '키워드': _all_keys,
                                        f'이번 {keyword_days}일': [_curr_ctr.get(k, 0) for k in _all_keys],
                                        f'이전 {keyword_days}일': [_prev_ctr.get(k, 0) for k in _all_keys],
                                    }).set_index('키워드')
                                    _fig_wk = px.imshow(
                                        _hm_df.T,
                                        labels=dict(x="키워드", y="기간", color="등장 횟수"),
                                        color_continuous_scale="RdYlGn",
                                        aspect="auto",
                                        text_auto=True,
                                    )
                                    _fig_wk.update_layout(
                                        height=250,
                                        plot_bgcolor='rgba(0,0,0,0)',
                                        paper_bgcolor='rgba(0,0,0,0)',
                                        font_color='#e8e8e8',
                                        margin=dict(l=20, r=20, t=20, b=60),
                                    )
                                    _fig_wk.update_xaxes(tickangle=-40)
                                    st.plotly_chart(_fig_wk, use_container_width=True)
                                    st.caption(
                                        f"이번 {keyword_days}일과 이전 {keyword_days}일의 기술 키워드 등장 횟수 비교. "
                                        "초록 = 증가, 빨강 = 감소."
                                    )
                                else:
                                    st.info("기술 키워드 데이터가 부족합니다.")
                            else:
                                st.info("비교할 이전 기간 데이터가 부족합니다. 기사가 더 누적되면 표시됩니다.")

                    else:
                        st.info("💡 지식 그래프 기능을 사용하려면 `pip install networkx pyvis` 를 실행하세요.")

                else:
                    st.info("ℹ️ 기업, 기술, 국가 엔티티 데이터가 포함된 최근 분석 뉴스가 없습니다. (엔진 업그레이드 이전 데이터만 존재할 수 있습니다)")
            
            else:
                st.info("AI가 추출한 키워드가 없습니다. 뉴스를 먼저 분석하세요.")
        
        except Exception as e:
            st.error(f"키워드 분석 중 오류: {str(e)}")
            st.error(traceback.format_exc())
    
    else:
        st.info("📭 최근 뉴스 데이터가 없습니다. 뉴스를 먼저 수집하세요.")

    # ===== AI 모델별 품질 대시보드 =====
    st.markdown("---")
    st.markdown("#### 🤖 AI 모델별 분석 품질")
    try:
        from sqlalchemy import func, case
        with get_db_session() as _mq_db:
            _model_rows = (
                _mq_db.query(
                    NewsArticle.ai_model,
                    func.count(NewsArticle.id).label('total'),
                    func.sum(
                        case(
                            (
                                (NewsArticle.extracted_keywords != None) &
                                (NewsArticle.extracted_keywords != ''),
                                1
                            ),
                            else_=0
                        )
                    ).label('with_kw'),
                )
                .filter(NewsArticle.ai_model != None)
                .group_by(NewsArticle.ai_model)
                .all()
            )

        if _model_rows:
            _mq_cols = st.columns(min(len(_model_rows), 4))
            _model_icons = {'openai': '🟢', 'claude': '🟠', 'gemini': '🔵', 'perplexity': '🟣'}
            for _ci, _row in enumerate(_model_rows):
                _icon = _model_icons.get(str(_row.ai_model).lower(), '⚪')
                _total = _row.total or 0
                _with_kw = int(_row.with_kw or 0)
                _ratio = (_with_kw / _total * 100) if _total > 0 else 0
                with _mq_cols[_ci % 4]:
                    st.metric(
                        label=f"{_icon} {str(_row.ai_model).upper()}",
                        value=f"{_ratio:.0f}%",
                        delta=f"키워드 추출 {_with_kw}/{_total}건",
                        delta_color="normal",
                        help=f"extracted_keywords 존재 비율. 전체 {_total}건 중 {_with_kw}건 정상 추출."
                    )
        else:
            st.info("AI 모델별 분석 데이터가 없습니다.")
    except Exception as _mq_err:
        st.warning(f"모델 품질 집계 오류: {_mq_err}")



# ===== 2. 뉴스 관리 페이지 (수정 버전 - 주차별 보고서 추가) =====
elif selected == "뉴스 관리":
    st.markdown('<h1 class="main-header">📰 뉴스 수집 및 분석 관리</h1>', unsafe_allow_html=True)
    
    if 'news_tab' not in st.session_state:
        st.session_state.news_tab = 'collect'
    
    col_tab1, col_tab2, col_tab3, col_tab4, col_spacer = st.columns([1, 1, 1, 1, 2])
    
    with col_tab1:
        if st.button("🔍 뉴스 수집", key="tab_collect", use_container_width=True):
            st.session_state.news_tab = 'collect'
    
    with col_tab2:
        if st.button("📋 전체 목록", key="tab_list", use_container_width=True):
            st.session_state.news_tab = 'list'
    
    with col_tab3:
        if st.button("🤖 AI 분석", key="tab_analyze", use_container_width=True):
            st.session_state.news_tab = 'analyze'
    
    with col_tab4:
        if st.button("📂 주차별 보고서", key="tab_weekly_reports", use_container_width=True):
            st.session_state.news_tab = 'weekly_reports'
    
    st.markdown("---")
    
    if st.session_state.news_tab == 'collect':
        st.markdown("### 🔍 뉴스 수집 실행")
        
        st.markdown("""
        <div class="info-card">
            <div class="info-card-title">💡 수집 정보</div>
            <div class="info-card-content">
                • <strong>수집 소스:</strong> 주요 기관 RSS + Naver News API<br>
                • <strong>수집 범위:</strong> 최근 48시간 이내 뉴스<br>
                • <strong>예상 소요 시간:</strong> 1~3분
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
        
        with col_btn1:
            if st.button("🚀 일일 뉴스 수집 시작", key="start_collect", type="primary", use_container_width=True):
                st.info("⏱️ 예상 소요 시간: 2~5분")
                
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                progress_text.text("🔍 뉴스 수집 중...")
                progress_bar.progress(0.5)
                
                with st.spinner("뉴스 수집 및 분석 중..."):
                    try:
                        import time
                        start_time = time.time()
                        
                        results = run_daily_collection()
                        
                        elapsed_time = time.time() - start_time
                        
                        progress_bar.progress(1.0)
                        progress_text.text("✅ 모든 작업 완료!")
                        
                        st.success(f"✅ 수집 완료! ({elapsed_time:.1f}초 소요)")
                        st.info(f"📊 분석된 뉴스: {len(results)}개")
                        st.balloons()
                    
                    except Exception as e:
                        st.error(f"❌ 오류 발생: {str(e)}")
        
        with col_btn2:
            if st.button("🔄 새로고침", key="refresh_collect", use_container_width=True):
                st.rerun()
        
        with col_btn3:
            if st.button("📊 통계 보기", key="view_stats", use_container_width=True):
                stats = get_db_statistics()
                st.info(f"총 {stats['total']}개 | 분석완료 {stats['analyzed']}개 | 대기 {stats['pending']}개")
    
    elif st.session_state.news_tab == 'list':
        st.markdown("### 📋 전체 뉴스 목록")
        
        col_filter1, col_filter2, col_filter3 = st.columns([1, 1, 2])
        
        with col_filter1:
            days_filter = st.selectbox("📅 기간", [1, 3, 7, 30, 90], index=2, key="filter_days")
        
        with col_filter2:
            status_filter = st.selectbox("📊 상태", ["전체", "분석완료", "미분석"], index=0, key="filter_status")
        
        with col_filter3:
            search_query = st.text_input("🔍 검색", placeholder="제목 또는 출처로 검색...", key="search_news")
        
        is_analyzed = None if status_filter == "전체" else (status_filter == "분석완료")
        all_news = load_news_from_db(days=days_filter, is_analyzed=is_analyzed)
        
        if search_query:
            all_news = [n for n in all_news if search_query.lower() in n['title'].lower() 
                        or search_query.lower() in n['source'].lower()]
        
        st.write(f"**총 {len(all_news)}개의 뉴스**")
        
        if all_news:
            try:
                df = pd.DataFrame(all_news)
                df['상태'] = df['is_analyzed'].apply(lambda x: '✅ 완료' if x else '⏳ 대기')
                
                display_df = df[['title', 'source', 'published', '상태']].rename(columns={
                    'title': '제목',
                    'source': '출처',
                    'published': '발행일'
                })
                
                st.dataframe(display_df, use_container_width=True, height=500)
            except Exception as e:
                st.error(f"데이터 표시 중 오류: {str(e)}")
        else:
            st.info("📭 조건에 맞는 뉴스가 없습니다.")
    
    elif st.session_state.news_tab == 'analyze':
        st.markdown("### 🤖 AI 분석 실행")
        
        unanalyzed = load_news_from_db(days=7, is_analyzed=False)
        cfg = load_config()
        
        st.markdown(f"""
        <div class="info-card">
            <div class="info-card-title">📊 분석 현황</div>
            <div class="info-card-content">
                • <strong>미분석 뉴스:</strong> {len(unanalyzed)}개<br>
                • <strong>AI 모델:</strong> {cfg.get('ai_model', 'openai').upper()}<br>
                • <strong>예상 소요 시간:</strong> 약 {len(unanalyzed[:10]) * 3}초
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if unanalyzed:
            num_to_analyze = st.slider("분석할 뉴스 개수", 1, min(20, len(unanalyzed)), 10, key="num_analyze")
            
            if st.button(f"🤖 상위 {num_to_analyze}개 분석 시작", type="primary", 
                         use_container_width=True, key="start_ai_analyze"):
                with st.spinner(f"AI 분석 중... ({num_to_analyze}개)"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    success_count = 0
                    
                    for i, article in enumerate(unanalyzed[:num_to_analyze]):
                        try:
                            status_text.text(f"분석 중: {article['title'][:50]}...")
                            
                            article['content'] = get_article_content(article['link'])
                            analysis = analyze_news_with_ai(article, ai_model=cfg.get('ai_model', 'openai'))
                            update_analysis_in_db(article['id'], analysis, cfg.get('ai_model', 'openai'))
                            
                            success_count += 1
                            progress_bar.progress((i + 1) / num_to_analyze)
                        except Exception:
                            st.warning(f"⚠️ 분석 실패: {article['title'][:30]}...")
                    
                    status_text.empty()
                    st.success(f"✅ {success_count}/{num_to_analyze}개 분석 완료!")
                    st.balloons()
                    st.rerun()
        else:
            st.success("🎉 모든 뉴스가 분석되었습니다!")
    
    # ===== ✅ 새로 추가: 주차별 보고서 탭 =====
    elif st.session_state.news_tab == 'weekly_reports':
        st.markdown("### 📂 주차별 보고서 조회 및 다운로드")
        
        st.markdown("""
        <div class="info-card">
            <div class="info-card-title">💡 주차별 보고서 안내</div>
            <div class="info-card-content">
                • <strong>자동 생성:</strong> 전체 프로세스 실행 시 자동으로 생성됩니다<br>
                • <strong>저장 위치:</strong> data/reports 폴더<br>
                • <strong>파일 형식:</strong> Excel (.xlsx)<br>
                • <strong>포함 내용:</strong> 뉴스 분석 결과 + 키워드 통계
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        reports_dir = Path("data/reports")
        
        if reports_dir.exists():
            excel_files = sorted(
                [f for f in reports_dir.glob("news_analysis_*.xlsx")],
                reverse=True
            )
            
            if excel_files:
                col_select, col_info = st.columns([2, 1])
                
                with col_select:
                    week_options = [f.stem.replace('news_analysis_', '') for f in excel_files]
                    selected_week = st.selectbox(
                        "📅 조회할 주차 선택",
                        options=week_options,
                        key="select_week_report",
                        help="ISO 8601 주차 형식 (YYYY_Www)"
                    )
                
                with col_info:
                    if selected_week:
                        try:
                            filepath = reports_dir / f"news_analysis_{selected_week}.xlsx"
                            df = pd.read_excel(filepath)
                            st.metric("📊 전체 뉴스 수", f"{len(df)}개")
                            st.caption(f"📁 파일 크기: {filepath.stat().st_size / 1024:.1f} KB")
                        except Exception as e:
                            st.error(f"파일 로드 오류: {e}")
                
                st.markdown("---")
                
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                
                with col_btn1:
                    if st.button("📊 데이터 미리보기", use_container_width=True, key="preview_week_data"):
                        try:
                            filepath = reports_dir / f"news_analysis_{selected_week}.xlsx"
                            df = pd.read_excel(filepath)
                            st.success(f"✅ {selected_week} 데이터 로드 완료 ({len(df)}개)")
                            st.dataframe(df, use_container_width=True, height=500)
                        except Exception as e:
                            st.error(f"❌ 데이터 로드 실패: {e}")
                
                with col_btn2:
                    # FIX: 파일 다운로드 오류 처리 강화
                    try:
                        filepath = reports_dir / f"news_analysis_{selected_week}.xlsx"
                        if not filepath.exists():
                            st.warning(f"⚠️ 파일이 존재하지 않습니다: {filepath.name}")
                        else:
                            with open(filepath, 'rb') as f:
                                file_bytes = f.read()
                            st.download_button(
                                label="💾 뉴스 분석 엑셀",
                                data=file_bytes,
                                file_name=filepath.name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_news_excel",
                                use_container_width=True
                            )
                    except OSError as e:
                        st.error(f"❌ 파일 읽기 실패: {e}")
                    except Exception as e:
                        st.error(f"❌ 다운로드 실패: {e}")
                
                with col_btn3:
                    try:
                        keyword_filepath = reports_dir / f"keyword_summary_{selected_week}.xlsx"
                        if keyword_filepath.exists():
                            with open(keyword_filepath, 'rb') as f:
                                st.download_button(
                                    label="📈 키워드 통계 엑셀",
                                    data=f,
                                    file_name=keyword_filepath.name,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key="download_keyword_excel",
                                    use_container_width=True
                                )
                        else:
                            st.button(
                                "📈 키워드 통계 없음",
                                disabled=True,
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"❌ 다운로드 실패: {e}")
                
                # ===== 키워드 통계 시각화 =====
                st.markdown("---")
                st.markdown("### 📈 키워드 통계 시각화")
                
                if st.button("📊 키워드 통계 보기", use_container_width=True, key="view_keyword_stats"):
                    try:
                        keyword_filepath = reports_dir / f"keyword_summary_{selected_week}.xlsx"
                        if keyword_filepath.exists():
                            df_keywords = pd.read_excel(keyword_filepath, sheet_name='전체 키워드')
                            df_summary = pd.read_excel(keyword_filepath, sheet_name='주간 통계')
                            
                            st.success(f"✅ {selected_week} 키워드 통계")
                            
                            col_chart, col_stats = st.columns([2, 1])
                            
                            with col_chart:
                                st.markdown("**📊 TOP 20 키워드**")
                                fig = px.bar(
                                    df_keywords.head(20),
                                    x='빈도',
                                    y='키워드',
                                    orientation='h',
                                    color='빈도',
                                    color_continuous_scale='Viridis',
                                    text='빈도'
                                )
                                fig.update_layout(
                                    height=500,
                                    yaxis={'categoryorder': 'total ascending'},
                                    showlegend=False
                                )
                                fig.update_traces(textposition='outside')
                                st.plotly_chart(fig, use_container_width=True)
                            
                            with col_stats:
                                st.markdown("**📈 주간 통계**")
                                for _, row in df_summary.iterrows():
                                    st.metric(row['항목'], row['값'])
                        else:
                            st.warning(f"⚠️ 키워드 통계 파일이 없습니다: {keyword_filepath.name}")
                    except Exception as e:
                        st.error(f"❌ 키워드 통계 로드 실패: {e}")
            else:
                st.info("📭 아직 생성된 주차별 보고서가 없습니다.")
                st.caption("💡 대시보드에서 '전체 프로세스 실행' 버튼을 클릭하여 첫 번째 보고서를 생성하세요.")
        else:
            st.info("📁 reports 폴더가 없습니다. 첫 번째 실행 후 자동으로 생성됩니다.")
            st.caption("💡 대시보드 → 전체 프로세스 실행으로 폴더가 자동 생성됩니다.")


# ===== 3. 리포트 페이지 =====
elif selected == "리포트":
    st.markdown('<h1 class="main-header">📊 리포트 생성 및 발송</h1>', unsafe_allow_html=True)
    
    # ===== 🔥 커스텀 탭 UI =====
    if 'report_tab' not in st.session_state:
        st.session_state.report_tab = 'daily'

    col_tab1, col_tab2, col_tab3, col_tab4, col_spacer = st.columns([1, 1, 1, 1.4, 1])

    with col_tab1:
        if st.button("📅 일일 리포트", key="tab_daily_report", use_container_width=True):
            st.session_state.report_tab = 'daily'

    with col_tab2:
        if st.button("📆 주간 리포트", key="tab_weekly_report", use_container_width=True):
            st.session_state.report_tab = 'weekly'

    with col_tab3:
        if st.button("📈 월간 리포트", key="tab_monthly_report", use_container_width=True):
            st.session_state.report_tab = 'monthly'

    with col_tab4:
        if st.button("🤖 자율 인텔리전스", key="tab_auto_intel", use_container_width=True):
            st.session_state.report_tab = 'auto_intel'

    st.markdown("---")
    
    # 탭 컨텐츠
    if st.session_state.report_tab == 'daily':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-card">
            <div class="info-card-title">📅 일일 리포트</div>
            <div class="info-card-content">
                오늘 수집한 뉴스를 분석하여 리포트를 생성하고 이메일로 발송합니다.<br>
                • <strong>대상:</strong> 오늘 수집된 뉴스<br>
                • <strong>형식:</strong> Google Docs + 이메일 HTML<br>
                • <strong>수신자:</strong> 설정된 이메일 목록
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if st.button("📧 일일 리포트 생성 및 발송", type="primary", use_container_width=True, key="send_daily"):
                with st.spinner("리포트 생성 중... (1~2분 소요)"):
                    try:
                        run_daily_collection()
                        st.success("✅ 일일 리포트 발송 완료!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"❌ 오류: {str(e)}")
        
        with col2:
            stats = get_db_statistics()
            st.metric("오늘 수집", f"{stats['today']}개")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    elif st.session_state.report_tab == 'weekly':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-card">
            <div class="info-card-title">📆 주간 트렌드 리포트</div>
            <div class="info-card-content">
                최근 7일간의 뉴스를 종합 분석하여 트렌드 리포트를 생성합니다.<br>
                • <strong>분석 기간:</strong> 최근 7일<br>
                • <strong>포함 내용:</strong> 키워드 트렌드, 주요 이슈, 시사점<br>
                • <strong>시각화:</strong> 트렌드 차트 포함
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        weekly_news = load_news_from_db(days=7, is_analyzed=True)
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if st.button("📧 주간 리포트 생성 및 발송", type="primary", use_container_width=True, key="send_weekly"):
                if len(weekly_news) < 5:
                    st.warning("⚠️ 분석된 뉴스가 부족합니다. 최소 5개 이상 필요합니다.")
                else:
                    with st.spinner("주간 리포트 생성 중..."):
                        try:
                            doc_url = run_weekly_report()
                            if doc_url:
                                st.success(f"✅ 주간 리포트 완료!")
                                st.markdown(f"[📄 구글 문서 보기]({doc_url})")
                        except Exception as e:
                            st.error(f"❌ 오류: {str(e)}")
        
        with col2:
            st.metric("분석된 뉴스", f"{len(weekly_news)}개")
        
        with col3:
            if st.button("📊 미리보기", use_container_width=True, key="preview_weekly"):
                if weekly_news:
                    st.write("**최근 7일 주요 뉴스:**")
                    for i, news in enumerate(weekly_news[:5], 1):
                        st.write(f"{i}. {news['title'][:60]}...")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    elif st.session_state.report_tab == 'monthly':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-card">
            <div class="info-card-title">📈 월간 종합 리포트</div>
            <div class="info-card-content">
                최근 30일간의 뉴스를 종합 분석하고 트렌드를 시각화합니다.<br>
                • <strong>분석 기간:</strong> 최근 30일<br>
                • <strong>포함 내용:</strong> 월간 트렌드, 이상 감지, 예측 분석<br>
                • <strong>시각화:</strong> 다양한 차트 및 인사이트
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        monthly_news = load_news_from_db(days=30, is_analyzed=True)
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if st.button("📧 월간 리포트 생성 및 발송", type="primary", use_container_width=True, key="send_monthly"):
                if len(monthly_news) < 10:
                    st.warning("⚠️ 분석된 뉴스가 부족합니다. 최소 10개 이상 필요합니다.")
                else:
                    with st.spinner("월간 리포트 생성 중..."):
                        try:
                            doc_url = run_monthly_report()
                            if doc_url:
                                st.success(f"✅ 월간 리포트 완료!")
                                st.markdown(f"[📄 구글 문서 보기]({doc_url})")
                        except Exception as e:
                            st.error(f"❌ 오류: {str(e)}")
        
        with col2:
            st.metric("분석된 뉴스", f"{len(monthly_news)}개")
        
        with col3:
            if st.button("📊 트렌드 보기", use_container_width=True, key="trend_monthly"):
                if monthly_news:
                    # 간단한 키워드 트렌드
                    all_titles = ' '.join([n['title'] for n in monthly_news])
                    words = all_titles.split()
                    word_freq = {}
                    for word in words:
                        if len(word) > 2:
                            word_freq[word] = word_freq.get(word, 0) + 1
                    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
                    
                    st.write("**월간 TOP 10 키워드:**")
                    for i, (word, count) in enumerate(top_words, 1):
                        st.write(f"{i}. {word} ({count}회)")
        
        st.markdown('</div>', unsafe_allow_html=True)

    elif st.session_state.report_tab == 'auto_intel':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)

        st.markdown("""
        <div class="info-card">
            <div class="info-card-title">🤖 자율 인텔리전스 리포트 (Phase 4)</div>
            <div class="info-card-content">
                급등 엔티티를 자동 감지하고, RAG 검색으로 심층 컨텍스트를 수집한 뒤,
                AI가 종합 분석 섹션을 리포트에 자동 주입합니다.<br>
                <br>
                <b>파이프라인:</b>
                데이터 로드 → 급등 감지 → RAG 검색 → AI 내러티브 → 리포트 생성 → 문서 추가 → 이메일 발송
            </div>
        </div>
        """, unsafe_allow_html=True)

        _ai_period = st.radio(
            "분석 기간",
            options=['weekly', 'monthly'],
            format_func=lambda x: '📆 주간 (최근 7일)' if x == 'weekly' else '📈 월간 (최근 30일)',
            horizontal=True,
            key="auto_intel_period",
        )
        _ai_skip_email = st.checkbox(
            "이메일 발송 건너뜀 (문서만 생성)",
            value=False,
            key="auto_intel_skip_email",
        )

        st.markdown("---")
        _ai_btn_col, _ai_info_col = st.columns([2, 1])

        with _ai_info_col:
            # Bug 7: is_analyzed 플래그 대신 extracted_keywords 존재 여부로 계산
            _ai_news_count = len([
                n for n in load_news_from_db(
                    days=7 if _ai_period == 'weekly' else 30
                ) if n.get('extracted_keywords')
            ])
            st.metric("활용 가능 기사", f"{_ai_news_count}개")
            if _ai_news_count < 5:
                st.warning("분석된 기사가 부족합니다 (최소 5개).")

        with _ai_btn_col:
            if st.button(
                "🚀 자율 인텔리전스 리포트 실행",
                type="primary",
                use_container_width=True,
                key="run_auto_intel",
                disabled=(_ai_news_count < 5),
            ):
                _progress_area = st.empty()
                _log_lines = []

                def _ui_progress(msg: str):
                    _log_lines.append(msg)
                    _progress_area.markdown(
                        '<div style="background:#1a1a2e;padding:12px;border-radius:8px;'
                        'font-family:monospace;font-size:0.85em;max-height:260px;overflow-y:auto;">'
                        + '<br>'.join(_log_lines[-15:])
                        + '</div>',
                        unsafe_allow_html=True,
                    )

                _result_placeholder = st.empty()

                with st.spinner("자율 인텔리전스 파이프라인 실행 중..."):
                    try:
                        from auto_intel_report import run_auto_intel_report
                        _final_state = run_auto_intel_report(
                            period=_ai_period,
                            progress_cb=_ui_progress,
                            skip_email=_ai_skip_email,
                        )

                        if _final_state.get('doc_url'):
                            _result_placeholder.success("✅ 자율 인텔리전스 리포트 완료!")
                            st.markdown(f"[📄 구글 문서 보기]({_final_state['doc_url']})")
                            st.balloons()

                            # 결과 요약 카드
                            _r1, _r2, _r3 = st.columns(3)
                            _r1.metric("급등 엔티티", f"{len(_final_state['surges'])}개")
                            _r2.metric("RAG 검색", f"{len(_final_state['rag_context'])}개")
                            _r3.metric("이메일", "✅ 발송" if _final_state['email_sent'] else "건너뜀")

                            if _final_state['surges']:
                                st.markdown("**📈 급등 엔티티 목록**")
                                for _s in _final_state['surges']:
                                    _pct = _s['pct_change']
                                    _pct_str = f"+{_pct*100:.0f}%" if _pct != float('inf') else "신규"
                                    _icon = {'company': '🏢', 'tech': '🛠️', 'country': '🌍'}.get(_s['node_type'], '📌')
                                    st.write(f"{_icon} **{_s['name']}** {_pct_str} ({_s['prev_count']}→{_s['curr_count']}회)")

                            if _final_state['errors']:
                                with st.expander("⚠️ 경고/오류 로그"):
                                    for err in _final_state['errors']:
                                        st.warning(err)
                        else:
                            _result_placeholder.error("❌ 리포트 생성 실패. 로그를 확인하세요.")
                            if _final_state['errors']:
                                for err in _final_state['errors']:
                                    st.error(err)

                    except Exception as e:
                        st.error(f"❌ 실행 오류: {e}")

        st.markdown('</div>', unsafe_allow_html=True)


# ===== 4. 뉴스 검색 (RAG) 페이지 =====
elif selected == "뉴스 검색":
    st.markdown('<h1 class="main-header">🔍 뉴스 자연어 검색</h1>', unsafe_allow_html=True)
    st.markdown("수집된 뉴스 DB를 자연어로 검색합니다. AI가 관련 기사를 찾아 종합 답변을 생성합니다.")

    try:
        from rag_search import answer_with_rag, get_embedding_stats, embed_unprocessed_articles
        from news_engine import run_batch_analysis_on_pending

        emb_stats = get_embedding_stats()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("AI 분석 기사", emb_stats['total_analyzed'], help="title+분석결과로 임베딩 (고품질)")
        c2.metric("본문 저장 기사", emb_stats['total_with_content'], help="title+본문으로 임베딩 (중품질)")
        c3.metric("품질필터 기사", emb_stats['total_quality'], help="title만으로 임베딩 (저품질)")
        c4.metric(
            "임베딩 완료",
            f"{emb_stats['total_embedded']} / {emb_stats['total_embeddable']}",
            delta=f"-{emb_stats['pending_embed']} 대기" if emb_stats['pending_embed'] > 0 else "완료",
        )

        # 배치 AI 분석 (품질필터 기사 → 고품질 임베딩으로 승격)
        with st.expander(f"🤖 배치 AI 분석 — 품질필터 미분석 기사 {emb_stats['total_quality']}건을 고품질 임베딩으로 승격"):
            st.caption(
                "AI 선별 통과 기사에 전체 분석을 수행합니다. "
                "분석 완료 기사는 'title+분석결과' 고품질 임베딩으로 자동 승격됩니다. "
                "기사 1건당 약 10~30초 소요 (모델에 따라 상이)."
            )
            ba_col1, ba_col2 = st.columns(2)
            batch_size = ba_col1.number_input("배치 크기 (건)", min_value=1, max_value=50, value=10, step=5)
            ba_model = ba_col2.selectbox(
                "AI 모델",
                ["openai", "gemini", "claude", "perplexity"],
                index=0,
                key="batch_analysis_model",
            )
            if st.button("▶ 배치 AI 분석 실행", type="primary", use_container_width=True):
                _progress_text = st.empty()
                _progress_bar = st.progress(0)

                def _on_progress(done, total):
                    _pct = int(done / total * 100) if total else 0
                    _progress_bar.progress(_pct)
                    _progress_text.caption(f"분석 중... {done}/{total}건")

                with st.spinner(f"AI 분석 실행 중 (최대 {batch_size}건)..."):
                    ba_result = run_batch_analysis_on_pending(
                        batch_size=int(batch_size),
                        ai_model=ba_model,
                        progress_callback=_on_progress,
                    )
                _progress_bar.empty()
                _progress_text.empty()

                if ba_result['analyzed'] > 0:
                    st.success(
                        f"✅ {ba_result['analyzed']}건 분석 완료 "
                        f"(실패: {ba_result['failed']}건 / 잔여: {ba_result['pending_after']}건)"
                    )
                    # 분석 완료 후 즉시 임베딩 처리
                    with st.spinner("신규 분석 기사 임베딩 처리 중..."):
                        emb_n = embed_unprocessed_articles(limit=ba_result['analyzed'] + 10)
                    st.info(f"📌 {emb_n}건 임베딩 추가 완료")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("분석된 기사가 없습니다. 잔여 대기 기사를 확인하세요.")

        # 임베딩 단독 처리 (분석 없이 커버리지만 확대)
        if emb_stats['pending_embed'] > 0:
            if st.button(f"⚡ 임베딩만 처리 — {emb_stats['pending_embed']}건 대기 (최대 100개/회)"):
                with st.spinner("임베딩 처리 중..."):
                    n = embed_unprocessed_articles(limit=100)
                st.success(f"{n}개 임베딩 완료!")
                st.cache_data.clear()
                st.rerun()

        st.markdown("---")

        with st.form("rag_search_form"):
            query = st.text_area(
                "검색 질문",
                placeholder="예: 지난 한 달간 6G 표준화 관련 주요 동향은?\n예: 국내 기업이 주도한 AI 반도체 소식은?",
                height=100,
            )
            submitted = st.form_submit_button("🔎 검색", use_container_width=True)

        if submitted and query.strip():
            with st.spinner("DB 전체 하이브리드 검색 및 답변 생성 중..."):
                result = answer_with_rag(query.strip(), top_k=15, days=None)

            st.markdown("### 💬 AI 종합 답변")
            st.markdown(result['answer'])

            if result['sources']:
                n_emb = sum(1 for r in result['sources'] if r.get('search_type') == 'embedding')
                n_kw  = sum(1 for r in result['sources'] if r.get('search_type') == 'keyword')
                st.caption(f"참고 기사 {len(result['sources'])}건 — 임베딩 유사도: {n_emb}건 · 키워드 매칭: {n_kw}건")
                st.markdown("### 📰 참고 기사")
                for i, art in enumerate(result['sources'], 1):
                    sim_pct = int(art.get('similarity', 0) * 100)
                    stype = art.get('search_type', 'embedding')
                    badge = "🔵 임베딩" if stype == 'embedding' else "🟡 키워드"
                    has_analysis = "📝" if art.get('analysis_result') else "📄"
                    _short_title = art['title'][:70] + ('…' if len(art['title']) > 70 else '')
                    with st.expander(f"{has_analysis} [{i}] {_short_title}"):
                        st.markdown(f"{badge} {sim_pct}%  |  **출처**: {art['source']}  |  **날짜**: {art['published']}")
                        if art.get('link'):
                            st.markdown(f"**링크**: [{art['link']}]({art['link']})")
                        if art.get('analysis_result'):
                            st.markdown("**분석 요약**")
                            st.markdown(art['analysis_result'][:600])
                        elif art.get('content'):
                            st.markdown("**본문 일부**")
                            st.markdown(art['content'][:400])
        elif submitted:
            st.warning("검색어를 입력해주세요.")

    except ImportError as e:
        st.error(f"RAG 모듈 로드 실패: {e}")
    except Exception as e:
        st.error(f"오류 발생: {e}")


# ===== 5. 이슈 추적 페이지 =====
elif selected == "이슈 추적":
    st.markdown('<h1 class="main-header">📈 이슈 추적 & 표준화 갭</h1>', unsafe_allow_html=True)

    try:
        from trend_analyzer import (
            load_recurring_issues, load_standardization_gaps, update_gap_status
        )

        tab_recurring, tab_gaps = st.tabs(["🔄 연속 등장 이슈", "📐 표준화 갭 현황"])

        # ── 연속 등장 이슈 탭 ────────────────────────────────────────────────
        with tab_recurring:
            st.markdown("2회 이상 반복 등장한 이슈입니다. 주의가 필요한 지속 트렌드를 나타냅니다.")
            min_count = st.slider("최소 등장 횟수", 2, 10, 2, key="min_count_slider")
            issues = load_recurring_issues(min_count=min_count)

            if not issues:
                st.info("해당 조건의 연속 이슈가 없습니다. 주간/월간 리포트를 생성하면 자동으로 누적됩니다.")
            else:
                import pandas as pd
                df = pd.DataFrame(issues)
                df.columns = ['이슈 제목', '중요도', '등장 횟수', '최초 감지', '최근 감지', '추세', 'TTA 대응']

                def _level_color(val):
                    colors = {'상': 'background-color:#ffcdd2', '중': 'background-color:#fff9c4', '하': 'background-color:#c8e6c9'}
                    return colors.get(val, '')

                def _trend_icon(val):
                    icons = {'상승': '📈 상승', '유지': '➡️ 유지', '하락': '📉 하락', '신규': '🆕 신규'}
                    return icons.get(val, val)

                df['추세'] = df['추세'].apply(_trend_icon)
                st.dataframe(
                    df.style.applymap(_level_color, subset=['중요도']),
                    use_container_width=True, hide_index=True
                )

        # ── 표준화 갭 탭 ────────────────────────────────────────────────────
        with tab_gaps:
            st.markdown("AI가 감지한 표준화 공백 영역 누적 현황입니다.")

            col_filter, col_btn = st.columns([3, 1])
            status_filter = col_filter.selectbox(
                "상태 필터", ["전체", "미해결", "진행중", "해결됨"], key="gap_status_filter"
            )
            gaps = load_standardization_gaps(
                status=None if status_filter == "전체" else status_filter
            )

            if not gaps:
                st.info("표준화 갭 데이터가 없습니다. 주간/월간 리포트를 생성하면 자동으로 누적됩니다.")
            else:
                for gap in gaps:
                    prio_color = {'상': '🔴', '중': '🟡', '하': '🟢'}.get(gap['priority'], '⚪')
                    status_color = {'미해결': '🔴', '진행중': '🟡', '해결됨': '✅'}.get(gap['status'], '⚪')
                    months = gap['months_open']

                    with st.expander(
                        f"{prio_color} [{gap['priority']}] {gap['area'][:60]}  "
                        f"| {status_color} {gap['status']} | {months}개월 경과"
                    ):
                        st.markdown(f"**발견 이슈**: {gap['source_issue']}")
                        st.markdown(f"**최초 감지**: {gap['first_detected']}  |  **최근 업데이트**: {gap['last_updated']}")
                        if gap['resolution_note']:
                            st.markdown(f"**해결 메모**: {gap['resolution_note']}")

                        new_status = st.selectbox(
                            "상태 변경", ["미해결", "진행중", "해결됨"],
                            index=["미해결", "진행중", "해결됨"].index(gap['status']),
                            key=f"gap_status_{gap['id']}"
                        )
                        note = st.text_input("해결 메모 (선택)", value=gap['resolution_note'], key=f"gap_note_{gap['id']}")
                        if st.button("저장", key=f"gap_save_{gap['id']}"):
                            update_gap_status(gap['id'], new_status, note)
                            st.success("저장됨!")
                            st.rerun()

    except ImportError as e:
        st.error(f"모듈 로드 실패: {e}")
    except Exception as e:
        st.error(f"오류 발생: {e}")


# ===== 6. 내 설정 페이지 =====
elif selected == "내 설정":
    st.markdown('<h1 class="main-header">👤 내 설정</h1>', unsafe_allow_html=True)
    st.markdown(f"**{_user_name}** ({_user_email}) 님의 개인 설정")
    st.markdown("---")

    current = load_user_settings(_user_email)

    from news_engine import CONFIG, NAVER_QUERIES, RECEIVER_EMAIL

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("키워드 설정")
        default_keywords = current.get('keywords') or NAVER_QUERIES or []
        keywords_input = st.text_area(
            "모니터링할 키워드 (줄바꿈으로 구분)",
            value="\n".join(default_keywords),
            height=200,
            key="user_keywords"
        )

        st.subheader("AI 모델 선택")
        model_options = ["gemini", "openai", "claude", "perplexity"]
        model_labels = {
            "gemini": "Gemini 2.5 Flash",
            "openai": "GPT-4o",
            "claude": "Claude Sonnet",
            "perplexity": "Perplexity sonar-pro"
        }
        current_model = current.get('ai_model', 'gemini')
        ai_model = st.radio(
            "분석에 사용할 AI 모델",
            options=model_options,
            index=model_options.index(current_model) if current_model in model_options else 0,
            format_func=lambda x: model_labels[x],
            key="user_ai_model"
        )

    with col2:
        st.subheader("리포트 수신 이메일")
        default_emails = current.get('email_recipients') or (
            [RECEIVER_EMAIL] if RECEIVER_EMAIL else []
        )
        emails_input = st.text_area(
            "수신 이메일 주소 (줄바꿈으로 구분)",
            value="\n".join(default_emails),
            height=120,
            key="user_emails"
        )

        st.subheader("자동 실행 설정")
        sched_daily = st.checkbox(
            "일일 뉴스 수집 (매일 09:00 KST)",
            value=current.get('schedule_daily', True),
            key="user_sched_daily"
        )
        sched_weekly = st.checkbox(
            "주간 리포트 이메일 (매주 월요일 09:00 KST)",
            value=current.get('schedule_weekly', True),
            key="user_sched_weekly"
        )

    st.markdown("---")
    if st.button("💾 설정 저장", type="primary", use_container_width=False):
        save_user_settings(_user_email, {
            'keywords': [k.strip() for k in keywords_input.split('\n') if k.strip()],
            'ai_model': ai_model,
            'email_recipients': [e.strip() for e in emails_input.split('\n') if e.strip()],
            'schedule_daily': sched_daily,
            'schedule_weekly': sched_weekly,
        })
        st.success("설정이 저장되었습니다.")
        st.rerun()


# ===== 7. 설정 페이지 =====
elif selected == "설정":
    st.markdown('<h1 class="main-header">⚙️ 시스템 설정</h1>', unsafe_allow_html=True)
    
    cfg = load_config()
    
    # ===== 🔥 커스텀 탭 UI =====
    if 'settings_tab' not in st.session_state:
        st.session_state.settings_tab = 'api'
    
    col_tab1, col_tab2, col_tab3, col_tab4, col_spacer = st.columns([1, 1, 1, 1, 2])
    
    with col_tab1:
        if st.button("🔑 API 키", key="tab_api_settings", use_container_width=True):
            st.session_state.settings_tab = 'api'
    
    with col_tab2:
        if st.button("🏷️ 키워드", key="tab_keywords_settings", use_container_width=True):
            st.session_state.settings_tab = 'keywords'
    
    with col_tab3:
        if st.button("📧 이메일", key="tab_email_settings", use_container_width=True):
            st.session_state.settings_tab = 'email'
    
    with col_tab4:
        if st.button("⏰ 스케줄", key="tab_schedule_settings", use_container_width=True):
            st.session_state.settings_tab = 'schedule'
    
    st.markdown("---")
    
    # 탭 컨텐츠
    if st.session_state.settings_tab == 'api':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown("### 🔑 AI API 키 설정")
        
        st.info("💡 API 키는 암호화되어 저장됩니다. 입력 후 반드시 저장 버튼을 클릭하세요.")
        
        # API 키 입력
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### OpenAI")
            openai_key = st.text_input(
                "API Key",
                value=cfg.get('openai_api_key', ''),
                type="password",
                key="openai_key_input",
                help="GPT-4o 모델 사용을 위한 API 키"
            )
            st.caption("[API 키 발급](https://platform.openai.com/api-keys)")
            
            st.markdown("#### Gemini")
            gemini_key = st.text_input(
                "API Key",
                value=cfg.get('gemini_api_key', ''),
                type="password",
                key="gemini_key_input",
                help="Gemini 2.5 Flash 모델 사용"
            )
            st.caption("[API 키 발급](https://aistudio.google.com/app/apikey)")
        
        with col2:
            st.markdown("#### Claude")
            claude_key = st.text_input(
                "API Key",
                value=cfg.get('claude_api_key', ''),
                type="password",
                key="claude_key_input",
                help="Claude Sonnet 4 모델 사용"
            )
            st.caption("[API 키 발급](https://console.anthropic.com/settings/keys)")
            
            st.markdown("#### Perplexity")
            perplexity_key = st.text_input(
                "API Key",
                value=cfg.get('perplexity_api_key', ''),
                type="password",
                key="perplexity_key_input",
                help="Perplexity AI 모델 사용"
            )
            st.caption("[API 키 발급](https://www.perplexity.ai/settings/api)")
        
        st.markdown("---")
        st.markdown("#### Naver News API")
        
        col3, col4 = st.columns(2)
        
        with col3:
            naver_id = st.text_input(
                "Client ID",
                value=cfg.get('naver_client_id', ''),
                key="naver_id_input"
            )
        
        with col4:
            naver_secret = st.text_input(
                "Client Secret",
                value=cfg.get('naver_client_secret', ''),
                type="password",
                key="naver_secret_input"
            )
            st.caption("[Naver API 신청](https://developers.naver.com/apps/#/register)")
        
        if st.button("💾 API 키 저장", type="primary", use_container_width=True, key="save_api_keys"):
            cfg.update({
                'openai_api_key': openai_key,
                'claude_api_key': claude_key,
                'gemini_api_key': gemini_key,
                'perplexity_api_key': perplexity_key,
                'naver_client_id': naver_id,
                'naver_client_secret': naver_secret
            })
            save_config(cfg)
            st.success("✅ API 키가 안전하게 저장되었습니다!")

        # ── 모델 연결 상태 확인 ──────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🔌 AI 모델 연결 상태")
        st.caption("실제 API 호출로 연결 여부를 확인합니다. 소량의 토큰이 소비됩니다.")

        if st.button("🔍 연결 상태 확인", use_container_width=True, key="check_model_status"):
            models = [
                ("OpenAI (GPT-4o)",    "openai"),
                ("Claude (Sonnet 4)",  "claude"),
                ("Gemini 2.5 Flash",   "gemini"),
                ("Perplexity (Sonar)", "perplexity"),
            ]
            cols = st.columns(len(models))
            for col, (label, model_key) in zip(cols, models):
                with col:
                    with st.spinner(f"{label} 확인 중…"):
                        ok, msg = check_model_health(model_key)
                    if ok:
                        st.success(f"✅ {label}")
                        st.caption("정상")
                    else:
                        st.error(f"❌ {label}")
                        st.caption(msg)
        else:
            # 저장된 상태 표시 (버튼 누르기 전 기본 안내)
            st.info("위 버튼을 눌러 각 모델의 API 연결을 테스트하세요.")

        st.markdown('</div>', unsafe_allow_html=True)
    
    elif st.session_state.settings_tab == 'keywords':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown("### 검색 키워드 관리")
        
        st.info("💡 주요기관 RSS URL과 Naver 검색 키워드를 관리합니다.")
        
        st.markdown("#### 주요기관 RSS")

        # 기본값 안전하게 가져오기
        default_google_rss = cfg.get('google_alerts_rss', [])
        if not default_google_rss:
            default_google_rss = GOOGLE_ALERTS_RSS_URLS

        # RSS 피드 키워드 미리보기 (feedparser 없이 캐시된 데이터 표시)
        if default_google_rss:
            with st.expander(f"📋 등록된 RSS 피드 키워드 미리보기 ({len(default_google_rss)}개)", expanded=False):
                import feedparser as _fp
                preview_rows = []
                for idx, url in enumerate(default_google_rss, 1):
                    if not url.strip():
                        continue
                    try:
                        _feed = _fp.parse(url.strip())
                        raw_title = _feed.feed.get('title', '')
                        keyword = raw_title.split(' - ', 1)[1].strip() if ' - ' in raw_title else (raw_title or '알 수 없음')
                        entry_count = len(_feed.entries)
                        preview_rows.append({"#": idx, "키워드": keyword, "항목 수": entry_count, "URL": url.strip()[:60] + "..."})
                    except Exception:
                        preview_rows.append({"#": idx, "키워드": "조회 실패", "항목 수": "-", "URL": url.strip()[:60] + "..."})
                if preview_rows:
                    import pandas as _pd
                    st.dataframe(_pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

        google_rss = st.text_area(
            "RSS URL (한 줄에 하나씩)",
            value='\n'.join(default_google_rss) if isinstance(default_google_rss, list) else default_google_rss,
            height=200
        )
        
        st.markdown("#### Naver 검색 키워드")
        
        # 기본값 안전하게 가져오기
        default_naver_queries = cfg.get('naver_queries', [])
        if not default_naver_queries:
            default_naver_queries = NAVER_QUERIES
        
        naver_keywords = st.text_area(
            "키워드 (한 줄에 하나씩)",
            value='\n'.join(default_naver_queries) if isinstance(default_naver_queries, list) else default_naver_queries,
            height=150
        )
        
        if st.button("💾 키워드 저장", key="save_keywords"):
            cfg['google_alerts_rss'] = [url.strip() for url in google_rss.split('\n') if url.strip()]
            cfg['naver_queries'] = [kw.strip() for kw in naver_keywords.split('\n') if kw.strip()]
            save_config(cfg)
            st.success("✅ 키워드가 저장되었습니다!")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    elif st.session_state.settings_tab == 'email':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown("### 이메일 설정")
        
        sender = st.text_input("발신자 이메일", value=cfg.get('gmail_sender', ''))
        password = st.text_input("Gmail 앱 비밀번호", value=cfg.get('gmail_password', ''), type="password")

        receivers = st.text_area(
            "수신자 이메일 (한 줄에 하나씩)",
            value='\n'.join(cfg.get('gmail_receivers', [])) if isinstance(cfg.get('gmail_receivers', []), list) else cfg.get('gmail_receivers', ''),
            height=150
        )

        st.markdown("---")
        st.markdown("### 🔔 구글챗 긴급 알림")
        st.markdown("중요도 '상' 이슈 감지 시 구글챗으로 즉시 알림을 발송합니다.")
        gchat_webhook = st.text_input(
            "Google Chat Webhook URL",
            value=cfg.get('google_chat_webhook', ''),
            placeholder="https://chat.googleapis.com/v1/spaces/...",
            type="password",
        )
        alert_level = st.selectbox(
            "알림 최소 중요도",
            ["상", "중"],
            index=["상", "중"].index(cfg.get('alert_impact_level', '상')),
        )

        if st.button("💾 이메일/알림 설정 저장"):
            cfg.update({
                'gmail_sender': sender,
                'gmail_password': password,
                'gmail_receivers': [email.strip() for email in receivers.split('\n') if email.strip()],
                'google_chat_webhook': gchat_webhook,
                'alert_impact_level': alert_level,
            })
            save_config(cfg)
            st.success("✅ 이메일 및 알림 설정이 저장되었습니다!")

        # 구글챗 테스트 발송
        if gchat_webhook and st.button("📨 구글챗 테스트 발송"):
            try:
                from news_engine import send_google_chat_alert
                send_google_chat_alert(
                    issue_title="[테스트] IRONAGE AI 알림 연결 확인",
                    issue_desc=["ㅇ 구글챗 Webhook 연결이 정상적으로 설정되었습니다."],
                    impact_level="상",
                )
                st.success("✅ 테스트 메시지 발송 완료!")
            except Exception as e:
                st.error(f"발송 실패: {e}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    elif st.session_state.settings_tab == 'schedule':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown("### 자동화 스케줄 설정")
        
        st.info("⚙️ Windows 작업 스케줄러를 사용하여 자동 실행을 설정합니다.")
        
        # 스케줄 시간 설정
        daily_time = st.time_input("일일 리포트 발송 시간", value=datetime.strptime("09:00", "%H:%M").time())
        
        weekly_day = st.selectbox("주간 리포트 발송 요일", 
                                  ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                                  index=0)
        weekly_time = st.time_input("주간 리포트 발송 시간", value=datetime.strptime("09:00", "%H:%M").time())
        
        monthly_day = st.number_input("월간 리포트 발송일", min_value=1, max_value=28, value=1)
        monthly_time = st.time_input("월간 리포트 발송 시간", value=datetime.strptime("09:00", "%H:%M").time())
        
        col_save, col_register = st.columns(2)
        with col_save:
            if st.button("💾 스케줄 저장", use_container_width=True):
                cfg.update({
                    'schedule_daily': daily_time.strftime("%H:%M"),
                    'schedule_weekly': f"{weekly_day} {weekly_time.strftime('%H:%M')}",
                    'schedule_monthly': f"{monthly_day} {monthly_time.strftime('%H:%M')}"
                })
                save_config(cfg)
                st.success("✅ 스케줄이 저장되었습니다!")
        with col_register:
            if st.button("⏰ Windows 작업 스케줄러 자동 등록", use_container_width=True):
                try:
                    from news_engine import setup_windows_schedule
                    setup_windows_schedule()
                    st.success("✅ Windows 작업 스케줄러 등록 완료! (일일/주간/월간 3개 작업)")
                except Exception as e:
                    st.error(f"❌ 스케줄러 등록 실패: {e}")
                    st.info("💡 관리자 권한으로 실행하거나 수동으로 설정하세요.")

        st.markdown("---")
        st.markdown("### 📖 Windows 작업 스케줄러 설정 가이드")
        
        with st.expander("자세한 설정 방법 보기"):
            st.markdown("""
            #### 1. 작업 스케줄러 열기
            - `Win + R` → `taskschd.msc` 입력 → 확인
            
            #### 2. 새 작업 만들기
            - 우측 '작업 만들기' 클릭
            
            #### 3. 일반 탭
            - 이름: `IRONAGE 일일 뉴스 수집`
            - 설명: `매일 자동으로 뉴스를 수집하고 분석합니다`
            - 사용자 로그온 여부에 관계없이 실행: 체크
            
            #### 4. 트리거 탭
            - 새로 만들기 클릭
            - **일일 리포트**: 매일, 시작 시간 09:00
            - **주간 리포트**: 매주, 월요일, 시작 시간 09:00
            - **월간 리포트**: 매월, 1일, 시작 시간 09:00
            
            #### 5. 동작 탭
            - 새로 만들기 클릭
            - 프로그램/스크립트: `python`
            - 인수 추가:
              - 일일: `news_engine.py daily`
              - 주간: `news_engine.py weekly`
              - 월간: `news_engine.py monthly`
            - 시작 위치: `C:\\py_temp\\ISSUETREND`
            
            #### 6. 조건 탭
            - 컴퓨터의 전원이 켜져 있을 때만 작업 시작: 해제
            
            #### 7. 설정 탭
            - 작업 실패 시 다시 시작 간격: 1분
            - 다시 시작 시도 횟수: 3회
            
            #### 8. 저장 및 테스트
            - 확인 클릭
            - 작업 목록에서 우클릭 → '실행'으로 테스트
            """)
            
            st.code("""
# 수동 실행 명령어 (PowerShell)

# 일일 수집
python news_engine.py daily

# 주간 리포트
python news_engine.py weekly

# 월간 리포트
python news_engine.py monthly
            """, language="powershell")
        
        st.markdown('</div>', unsafe_allow_html=True)
