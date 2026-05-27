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
        get_unit_display_name,
        get_all_units,
        load_unit_settings,
        assign_user_unit,
        run_unit_collection,
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
        NAVER_QUERIES,
        get_all_active_keywords,
        filter_articles_by_keywords,
    )
except ImportError as e:
    st.error(f"❌ 모듈 import 실패: {e}")
    st.info("news_engine.py 파일이 같은 폴더에 있는지 확인하세요.")
    st.stop()

try:
    from intelligence_widgets import render_keyword_intelligence
    _INTEL_WIDGET_OK = True
except ImportError:
    _INTEL_WIDGET_OK = False

# ===== 페이지 설정 =====
st.set_page_config(
    page_title="IRONAGE AI Analytics",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== Google OAuth 인증 =====
# st.user (Streamlit 1.37.0+) — st.experimental_user는 1.50.0에서 제거됨.
# Google OAuth client_id/secret이 secrets에 없으면 _auth_enabled=False (로컬 모드).
_auth_enabled = False
try:
    if hasattr(st, 'user'):
        _auth_enabled = hasattr(st.user, 'is_logged_in')
except Exception:
    _auth_enabled = False

if _auth_enabled:
    if not st.user.is_logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("## IRONAGE AI Analytics")
            st.markdown("### TTA ICT 뉴스 인텔리전스 시스템")
            st.markdown("---")
            if st.button("🔑 Google 계정으로 로그인", use_container_width=True, type="primary"):
                st.login()
            st.caption("@tta.or.kr 계정만 접속 가능합니다.")
        st.stop()

    _user_email = st.user.email or ""
    _user_name  = st.user.name  or _user_email

    if not _user_email.endswith("@tta.or.kr"):
        st.error(f"접근 거부: {_user_email} 은(는) TTA 임직원 계정이 아닙니다.")
        st.info("@tta.or.kr 계정으로 다시 로그인해 주세요.")
        if st.button("로그아웃"):
            st.logout()
        st.stop()
else:
    # 로컬 개발 모드 또는 OAuth 미설정 — 테스트 유저 전환 가능
    _user_email = st.session_state.get("_test_user_email", "local@tta.or.kr")
    _user_name  = f"[테스트] {_user_email.split('@')[0]}"

# 관리자 이메일 목록 — 운영 관리/시스템 설정 탭 접근 가능
_ADMIN_EMAILS = {"ironage@tta.or.kr", "local@tta.or.kr"}
_is_admin = _user_email in _ADMIN_EMAILS

# ── 단(Unit) 감지 ──────────────────────────────────────────────────────────────
# 이메일이 바뀔 때마다 (테스트 전환 포함) unit 정보를 새로 로드한다.
# session_state 키: "_unit_id" (int|None), "_unit_display_name" (str)
_cached_email = st.session_state.get("_unit_cache_email")
if _cached_email != _user_email:
    # 이메일이 바뀌었거나 첫 로드 → DB에서 unit 정보 갱신
    try:
        _s = load_user_settings(_user_email)
        _uid = _s.get("unit_id")           # int or None
        _uname = get_unit_display_name(_uid) if _uid else ""
    except Exception:
        _uid, _uname = None, ""
    st.session_state["_unit_id"]           = _uid
    st.session_state["_unit_display_name"] = _uname
    st.session_state["_unit_cache_email"]  = _user_email

_unit_id           = st.session_state["_unit_id"]            # int or None
_unit_display_name = st.session_state["_unit_display_name"]  # "AI융합표준단" or ""
# ──────────────────────────────────────────────────────────────────────────────


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
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=block');

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
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown strong {
        color: white !important;
    }

    /* 사이드바 라디오 버튼 — 메뉴 스타일 */
    section[data-testid="stSidebar"] .stRadio > div {
        gap: 2px !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        display: flex !important;
        align-items: center !important;
        padding: 8px 14px !important;
        border-radius: 8px !important;
        color: #cbd5e1 !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        transition: background 0.15s, color 0.15s !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        background-color: rgba(255,255,255,0.08) !important;
        color: white !important;
    }
    section[data-testid="stSidebar"] .stRadio label[data-checked="true"],
    section[data-testid="stSidebar"] .stRadio input:checked + div {
        background-color: rgba(0,90,171,0.55) !important;
        color: white !important;
        font-weight: 700 !important;
    }
    /* 라디오 동그라미 숨기기 — 메뉴처럼 보이도록 */
    section[data-testid="stSidebar"] .stRadio input[type="radio"] {
        display: none !important;
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

    /* ===================================================================
       Material Symbols 텍스트 노출 완전 차단 + CSS-only 화살표로 대체
       Google Fonts 미로드 환경(방화벽 등)에서도 정상 동작
       =================================================================== */

    /* expander summary 레이아웃 */
    [data-testid="stExpander"] details summary {
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        gap: 6px !important;
        overflow: visible !important;
        position: relative !important;
        padding: 0.6rem 0.75rem !important;
    }

    /* summary 내부 레이블 — 남은 공간을 채우도록 */
    [data-testid="stExpander"] details summary > div,
    [data-testid="stExpander"] details summary > p {
        flex: 1 !important;
        min-width: 0 !important;
        overflow: visible !important;
        margin: 0 !important;
    }
    [data-testid="stExpander"] details summary p {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.5 !important;
    }

    /* expander 간격 */
    [data-testid="stExpander"] {
        margin-bottom: 0.5rem !important;
        overflow: visible !important;
    }

    /* ── Material Symbols 아이콘 텍스트 차단 (summary 헤더 내부 한정) ── */
    /* Streamlit이 keyboard_arrow_right / keyboard_arrow_down 텍스트를
       Material Symbols 폰트로 렌더링하는데, 폰트 미로드 시 텍스트 노출됨.
       font-size:0 으로 텍스트를 숨기고 ::before CSS 삼각형으로 대체. */
    [data-testid="stExpander"] details summary span[data-testid="stIconMaterial"] {
        font-size: 0 !important;
        min-width: 1.1rem !important;
        width: 1.1rem !important;
        height: 1.1rem !important;
        flex-shrink: 0 !important;
        position: relative !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    /* 닫힌 상태 → ▶ 오른쪽 방향 삼각형 */
    [data-testid="stExpander"] details:not([open]) summary span[data-testid="stIconMaterial"]::before {
        content: "" !important;
        display: block !important;
        width: 0 !important;
        height: 0 !important;
        border-top: 5px solid transparent !important;
        border-bottom: 5px solid transparent !important;
        border-left: 7px solid #64748b !important;
        flex-shrink: 0 !important;
    }

    /* 열린 상태 → ▼ 아래 방향 삼각형 */
    [data-testid="stExpander"] details[open] summary span[data-testid="stIconMaterial"]::before {
        content: "" !important;
        display: block !important;
        width: 0 !important;
        height: 0 !important;
        border-left: 5px solid transparent !important;
        border-right: 5px solid transparent !important;
        border-top: 7px solid #64748b !important;
        flex-shrink: 0 !important;
    }

    /* ── 탭 스크롤 버튼 내 아이콘 텍스트 차단 ── */
    .stTabs [data-baseweb="tab-list"] > button span[data-testid="stIconMaterial"] {
        font-size: 0 !important;
    }
    .stTabs [data-baseweb="tab-list"] > button:first-child span[data-testid="stIconMaterial"]::before {
        content: "◀" !important;
        font-size: 0.75rem !important;
        color: #64748b !important;
    }
    .stTabs [data-baseweb="tab-list"] > button:last-child span[data-testid="stIconMaterial"]::before {
        content: "▶" !important;
        font-size: 0.75rem !important;
        color: #64748b !important;
    }

    /* ── Bootstrap Icons 잔류 CSS 전역 차단 (캐시 대비) ── */
    [class^="bi-"]::before, [class*=" bi-"]::before,
    [class^="bi-"]::after,  [class*=" bi-"]::after {
        display: none !important;
        content: none !important;
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
    if _unit_display_name:
        st.caption(f"🏢 {_unit_display_name}")
    elif _is_admin:
        st.caption("🛠️ 관리자")
    else:
        st.caption("⚠️ 단 미배정")
    if _auth_enabled:
        if st.button("로그아웃", use_container_width=True, key="sidebar_logout"):
            st.logout()
    st.markdown("---")

    # ── 🧪 테스트 유저 전환 (로컬 모드 전용) ─────────────────────────────────
    if not _auth_enabled:
        st.caption("🧪 테스트 유저 전환")
        _TEST_USERS = [
            "local@tta.or.kr",
            "ironage@tta.or.kr",
            "planning@tta.or.kr",
            "innovation@tta.or.kr",
            "ai@tta.or.kr",
            "radio@tta.or.kr",
        ]
        _TEST_LABELS = [
            "local@tta.or.kr (관리자)",
            "ironage@tta.or.kr (관리자)",
            "planning@tta.or.kr (표준기획단)",
            "innovation@tta.or.kr (표준혁신단)",
            "ai@tta.or.kr (AI융합표준단)",
            "radio@tta.or.kr (전파네트워크표준단)",
        ]
        _cur_email = st.session_state.get("_test_user_email", "local@tta.or.kr")
        _cur_idx = _TEST_USERS.index(_cur_email) if _cur_email in _TEST_USERS else 0
        _sel_label = st.selectbox(
            "테스트 유저",
            _TEST_LABELS,
            index=_cur_idx,
            key="test_user_select",
            label_visibility="collapsed",
        )
        _sel_email = _TEST_USERS[_TEST_LABELS.index(_sel_label)]
        if _sel_email != _cur_email:
            st.session_state["_test_user_email"] = _sel_email
            st.rerun()
        st.markdown("---")
    # ─────────────────────────────────────────────────────────────────────────

    _user_options = ["🏠 홈", "📰 내 뉴스피드", "🔍 AI 검색", "📊 리포트", "📈 트렌드 분석", "⚙️ 내 설정"]
    _admin_options = ["🛠️ 운영 대시보드", "📋 뉴스 관리", "⚙️ 시스템 설정"]

    _all_options = _user_options + (_admin_options if _is_admin else [])

    st.markdown("**메뉴**")
    selected = st.radio(
        "nav",
        options=_all_options,
        label_visibility="collapsed",
        key="main_nav",
    )

    if _is_admin:
        st.caption("🛠 운영 대시보드 / 뉴스 관리 / 시스템 설정은 관리자 전용입니다.")

    st.markdown("---")
    st.markdown("**한국정보통신기술협회(TTA)**")
    st.markdown("표준화본부 이동통신표준팀")
    st.markdown(f"*{datetime.now().strftime('%Y-%m-%d %H:%M')}*")


# ===== 홈 페이지 헬퍼 =====
def _render_unit_articles(articles: list, unit_display: str, max_cards: int = 8):
    """단별 분석 기사 카드를 렌더링한다."""
    analyzed = [a for a in articles if a.get('is_analyzed')][:max_cards]
    if not analyzed:
        st.info(f"최근 3일간 **{unit_display}** 분석 기사가 없습니다.\n\n"
                "⚙️ 시스템 설정에서 RSS/키워드를 확인하거나 관리자에게 수집 실행을 요청하세요.")
        return
    cards = []
    for art in analyzed:
        try:
            data = json.loads(art.get('analysis_result') or '{}')
        except Exception:
            data = {}
        title    = art.get('title', '제목 없음')
        source   = art.get('source', '')
        raw_main = data.get('main_content', '') or ''
        summary  = (raw_main[:280] + '…') if len(raw_main) > 280 else raw_main
        link     = art.get('link', '')
        date_str = str(art.get('collected_at', ''))[:10]
        impact   = data.get('impact_level', '')
        impact_color = {'Critical': '#dc2626', 'High': '#ea580c',
                        'Medium': '#2563eb', 'Low': '#64748b'}.get(impact, '#64748b')
        impact_badge = (f'<span style="background:{impact_color};color:#fff;'
                        f'font-size:0.7rem;padding:1px 7px;border-radius:99px;'
                        f'font-weight:600;">{impact}</span> ') if impact else ''
        link_tag = (f'<a href="{link}" target="_blank" '
                    f'style="color:#005aab;text-decoration:none;font-size:0.82rem;">🔗 원문</a>'
                    if link else '')
        cards.append(f"""
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;
            margin-bottom:10px;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
  <div style="font-size:0.76rem;font-weight:700;color:#005aab;
              margin-bottom:4px;">[{source}] {impact_badge}</div>
  <div style="font-weight:600;color:#1e293b;font-size:0.96rem;
              line-height:1.5;margin-bottom:7px;">{title}</div>
  <div style="font-size:0.87rem;color:#475569;line-height:1.65;
              margin-bottom:9px;">{summary}</div>
  <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;">
    {link_tag}
    <span style="color:#94a3b8;font-size:0.76rem;">수집: {date_str}</span>
  </div>
</div>""")
    st.markdown('\n'.join(cards), unsafe_allow_html=True)


# ===== 1. 홈 페이지 (모든 사용자) =====
if selected == "🏠 홈":
    st.markdown('<h1 class="main-header">🏠 IRONAGE 뉴스 인텔리전스</h1>', unsafe_allow_html=True)
    st.markdown(f"안녕하세요, **{_user_name}** 님! ({_unit_display_name or ('관리자' if _is_admin else '단 미배정')})")
    st.markdown("---")

    # ── 전체 통계 ──────────────────────────────────────────────────────────────
    _hs = get_db_statistics()
    _hc1, _hc2, _hc3, _hc4 = st.columns(4)
    _hc1.metric("오늘 수집", _hs['today'])
    _hc2.metric("분析 완료", _hs['analyzed'])
    _hc3.metric("전체 기사", _hs['total'])
    _hc4.metric("대기 중", _hs['pending'])

    # ── GAP 1: 전체 프로세스 실행 (관리자 전용) ────────────────────────────────
    if _is_admin:
        st.markdown("---")
        with st.expander("🚀 전체 프로세스 실행 (관리자 전용)", expanded=False):
            st.markdown("""
            **1단계:** 뉴스 수집 (Google Alerts + Naver) → DB 저장
            **2단계:** AI 뉴스 선별 (중요도 평가)
            **3단계:** 심층 분析 (본문 수집 + AI 분析 + 키워드 추출)
            **4단계:** 구글 문서 생성
            **5단계:** 이메일 자동 발송
            **6~7단계:** 주간 엑셀 + 키워드 통계 자동 저장
            *⏱️ 예상 소요 시간: 30분 이내*
            """)
            _home_num_analyze = st.slider("📊 분析할 뉴스 개수", 5, 20, 10, key="home_full_process_slider")
            if st.button("🚀 전체 프로세스 시작", type="primary",
                         use_container_width=True, key="home_full_process_start"):
                _home_progress = st.progress(0)
                _home_status = st.empty()
                try:
                    _home_cfg = load_config()
                    _home_model = _home_cfg.get('ai_model', 'openai')
                    st.info(f"🤖 사용 AI 모델: **{_home_model.upper()}**")

                    _home_status.markdown("### 📡 1/7: 뉴스 수집 중...")
                    _home_progress.progress(0.10)
                    _home_items = get_news_data()
                    _home_saved = save_news_to_db(_home_items)
                    st.success(f"✅ 1단계: {len(_home_items)}개 수집, {_home_saved}개 저장")
                    _home_progress.progress(0.15)

                    _home_status.markdown("### 🤖 2/7: AI 선별 중...")
                    _home_selected = filter_news_by_ai(_home_items, ai_model=_home_model, max_results=50)
                    st.success(f"✅ 2단계: {len(_home_selected)}개 선별")
                    _home_progress.progress(0.30)

                    _home_status.markdown("### 📝 3/7: 심층 분析 중...")
                    _home_pool = _home_selected[_home_num_analyze:] + [
                        item for item in _home_items
                        if item['link'] not in {n['link'] for n in _home_selected}
                    ]

                    def _home_progress_cb(done, total):
                        _home_progress.progress(0.35 + 0.25 * (done / total))
                        _home_status.markdown(f"### 📝 3/7: 심층 분析 중... ({done}/{total})")

                    _home_analyzed = analyze_news_with_replacement(
                        _home_selected[:_home_num_analyze], _home_pool,
                        target_count=_home_num_analyze, ai_model=_home_model,
                        progress_callback=_home_progress_cb,
                    )
                    st.success(f"✅ 3단계: {len(_home_analyzed)}개 분析")
                    _home_progress.progress(0.60)

                    _home_status.markdown("### 📄 4/7: 구글 문서 생성 중...")
                    _home_doc_url, _home_report_title = generate_google_doc_report(_home_analyzed)
                    if not _home_report_title:
                        import datetime as _hdt
                        _home_report_title = (
                            f"전파·이동통신 동향 보고서 "
                            f"({_hdt.date.today().strftime('%Y년 %m월 %d일')})"
                        )
                    if _home_doc_url:
                        st.success("✅ 4단계: 문서 생성 완료")
                        st.markdown(f"[📄 구글 문서 보기]({_home_doc_url})")
                    else:
                        st.warning("⚠️ 4단계: Google Docs 생성 실패")
                    _home_progress.progress(0.75)

                    _home_status.markdown("### 📧 5/7: 이메일 발송 중...")
                    _home_analyzed_links = {r['link'] for r in _home_analyzed}
                    _home_remaining = [n for n in _home_selected
                                       if n['link'] not in _home_analyzed_links]
                    send_gmail_report(_home_report_title, _home_analyzed,
                                      _home_doc_url, _home_remaining)
                    st.success("✅ 5단계: 이메일 발송 완료")
                    _home_progress.progress(0.85)

                    _home_status.markdown("### 📊 6/7: 주간 엑셀 저장 중...")
                    _home_year, _home_week, _home_week_str = get_week_number()
                    _home_excel = save_analysis_to_weekly_excel(_home_analyzed)
                    if _home_excel:
                        st.success(f"✅ 6단계: 주간 엑셀 저장 완료 ({_home_week_str})")
                    _home_progress.progress(0.93)

                    _home_status.markdown("### 📈 7/7: 키워드 통계 저장 중...")
                    _home_kw_path = save_keyword_summary_to_weekly_excel()
                    if _home_kw_path:
                        st.success("✅ 7단계: 키워드 통계 저장 완료")
                    _home_progress.progress(1.0)

                    _home_status.markdown("### ✅ 전체 프로세스 완료!")
                    st.success("🎉 모든 작업이 완료되었습니다!")
                    st.balloons()
                except Exception as _home_err:
                    st.error(f"❌ 오류: {str(_home_err)}")
                    st.error(traceback.format_exc())

    st.markdown("---")
    st.markdown("### 🏢 단별 일일 동향")

    # ── 4개 단 탭 ──────────────────────────────────────────────────────────────
    _ALL_UNITS = get_all_units()

    if not _ALL_UNITS:
        st.warning("단 정보를 불러올 수 없습니다. DB 연결을 확인하세요.")
    else:
        _tab_labels = []
        for _u in _ALL_UNITS:
            _mark = " ★" if _u['id'] == _unit_id else ""
            _tab_labels.append(f"{_u['display_name']}{_mark}")

        _tabs = st.tabs(_tab_labels)

        for _tab, _unit in zip(_tabs, _ALL_UNITS):
            with _tab:
                # 단별 최근 3일 기사 로드
                _unit_news = load_news_from_db(days=3, unit_id=_unit['id'])
                _analyzed_count = sum(1 for a in _unit_news if a.get('is_analyzed'))

                # GAP 2: 단 설명 + 키워드 현황 + 기사 수 통계
                _desc = _unit.get('description', '')
                _unit_cfg = load_unit_settings(_unit['id'])
                _unit_kws = _unit_cfg.get('keywords', [])

                _col_info, _col_cnt = st.columns([3, 1])
                with _col_info:
                    if _desc:
                        st.caption(f"📋 {_desc}")
                    if _unit_kws:
                        _kw_badges = " ".join(
                            f'<span style="background:#e8f0fe;color:#005aab;font-size:0.75rem;'
                            f'padding:1px 8px;border-radius:99px;margin:2px;display:inline-block;">'
                            f'{k}</span>'
                            for k in _unit_kws[:10]
                        )
                        st.markdown(
                            f"**🔑 모니터링 키워드:** {_kw_badges}", unsafe_allow_html=True
                        )
                    else:
                        st.caption("⚠️ 키워드 미설정 — ⚙️ 시스템 설정에서 단 키워드를 추가하세요.")
                with _col_cnt:
                    st.metric(
                        label="수집/분析",
                        value=f"{len(_unit_news)}건",
                        delta=f"분析 {_analyzed_count}건",
                        delta_color="normal",
                        help="최근 3일 기준"
                    )

                _render_unit_articles(_unit_news, _unit['display_name'])

    # ── GAP 3: 인텔리전스 대시보드 ────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 인텔리전스 대시보드")
    if _INTEL_WIDGET_OK:
        render_keyword_intelligence("home")
    else:
        st.warning(
            "⚠️ intelligence_widgets.py 모듈을 불러오지 못했습니다. "
            "운영 대시보드에서 확인하세요."
        )


# ===== 2. 내 뉴스피드 (모든 사용자 - 키워드 필터) =====
elif selected == "📰 내 뉴스피드":
    st.markdown('<h1 class="main-header">📰 내 뉴스피드</h1>', unsafe_allow_html=True)

    _feed_settings = load_user_settings(_user_email)
    _feed_keywords = _feed_settings.get('keywords') or list(NAVER_QUERIES) or []

    _f_col1, _f_col2 = st.columns([3, 1])
    with _f_col1:
        if _feed_keywords:
            st.markdown(f"**모니터링 키워드:** {', '.join(_feed_keywords)}")
        else:
            st.info("키워드가 설정되지 않았습니다. **⚙️ 내 설정**에서 키워드를 추가하세요.")
    with _f_col2:
        _feed_days = st.selectbox("기간", [1, 3, 7, 14], index=1, format_func=lambda x: f"최근 {x}일", key="feed_days")

    st.markdown("---")

    _feed_all = load_news_from_db(days=_feed_days)
    _feed_news = filter_articles_by_keywords(_feed_all, _feed_keywords) if _feed_keywords else _feed_all
    _feed_analyzed = [n for n in _feed_news if n.get('is_analyzed')]
    _feed_others   = [n for n in _feed_news if not n.get('is_analyzed')]

    st.markdown(f"**분석 완료 {len(_feed_analyzed)}건** / 수집 {len(_feed_news)}건 (최근 {_feed_days}일)")

    if _feed_analyzed:
        _feed_cards = []
        for _f_art in _feed_analyzed[:30]:
            try:
                _f_data = json.loads(_f_art.get('analysis_result') or '{}')
            except Exception:
                _f_data = {}
            _f_title  = _f_art.get('title', '제목 없음')
            _f_source = _f_art.get('source', '')
            _f_main_raw = _f_data.get('main_content', '') or ''
            _f_main   = (_f_main_raw[:400] + '...') if len(_f_main_raw) > 400 else _f_main_raw
            _f_impl_raw = _f_data.get('implications', '') or ''
            _f_impl   = (_f_impl_raw[:300] + '...') if len(_f_impl_raw) > 300 else _f_impl_raw
            _f_action = _f_data.get('tta_action_item', '') or ''
            _f_link   = _f_art.get('link', '')
            _f_date   = str(_f_art.get('collected_at', ''))[:10]
            _f_link_tag = (f'<a href="{_f_link}" target="_blank" '
                           f'style="color:#005aab;text-decoration:none;font-size:0.85rem;">🔗 원문 보기</a>'
                           if _f_link else '')
            _impl_block = (f'<div style="margin-top:6px;font-size:0.85rem;color:#64748b;">'
                           f'<strong>시사점:</strong> {_f_impl}</div>' if _f_impl else '')
            _action_block = (f'<div style="margin-top:4px;font-size:0.85rem;color:#64748b;">'
                             f'<strong>TTA 조치:</strong> {_f_action}</div>' if _f_action else '')
            _feed_cards.append(f"""
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;
            margin-bottom:10px;background:#ffffff;box-shadow:0 1px 4px rgba(0,0,0,0.05);">
  <div style="font-size:0.78rem;font-weight:700;color:#005aab;
              margin-bottom:4px;letter-spacing:0.02em;">[{_f_source}]</div>
  <div style="font-weight:600;color:#1e293b;font-size:0.97rem;
              line-height:1.5;margin-bottom:8px;">{_f_title}</div>
  <div style="font-size:0.88rem;color:#475569;line-height:1.65;">{_f_main}</div>
  {_impl_block}
  {_action_block}
  <div style="margin-top:10px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
    {_f_link_tag}
    <span style="color:#94a3b8;font-size:0.78rem;">수집일: {_f_date}</span>
  </div>
</div>""")
        st.markdown('\n'.join(_feed_cards), unsafe_allow_html=True)
    elif _feed_news:
        st.info(f"수집된 기사 {len(_feed_news)}건이 있지만 아직 AI 분석이 완료되지 않았습니다.")
    else:
        st.warning("해당 기간에 키워드에 맞는 기사가 없습니다.")


# ===== 운영 대시보드 (관리자 전용) =====
elif selected == "🛠️ 운영 대시보드":
    st.markdown('<h1 class="main-header">🛠️ 운영 대시보드</h1>', unsafe_allow_html=True)

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
            _urgent_html = '<div style="background-color: #fff1f2; padding: 15px; border-radius: 12px; border-left: 6px solid #dc2626; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">'
            for urgent in sorted_urgent[:5]:
                impact = _get_impact_info(urgent)
                level = impact['impact_level']
                icon = "🚨" if level == 'Critical' else "⚠️"
                color = "#dc2626" if level == 'Critical' else "#ea580c"
                src = (urgent.get('source') or '').replace('<', '&lt;').replace('>', '&gt;')
                ttl = (urgent.get('title') or '').replace('<', '&lt;').replace('>', '&gt;')
                _urgent_html += (
                    f'<p style="margin:8px 0;"><strong>{icon} '
                    f'<span style="color:{color};">[{level}]</span> [{src}] {ttl}</strong></p>'
                )
                if impact['tta_action_item']:
                    act = impact['tta_action_item'].replace('<', '&lt;').replace('>', '&gt;')
                    _urgent_html += (
                        f'<p style="margin-left:32px;margin-top:4px;margin-bottom:12px;'
                        f'font-size:14.5px;font-weight:600;color:#334155;">▶ TTA 조치: {act}</p>'
                    )
            _urgent_html += '</div>'
            st.markdown(_urgent_html, unsafe_allow_html=True)

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



# ===== 뉴스 관리 페이지 (관리자 전용) =====
elif selected == "📋 뉴스 관리":
    st.markdown('<h1 class="main-header">📋 뉴스 수집 및 분석 관리</h1>', unsafe_allow_html=True)
    
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


# ===== 리포트 페이지 =====
elif selected == "📊 리포트":
    st.markdown('<h1 class="main-header">📊 리포트 생성 및 발송</h1>', unsafe_allow_html=True)
    
    # ===== 🔥 커스텀 탭 UI =====
    if 'report_tab' not in st.session_state:
        st.session_state.report_tab = 'weekly'

    col_tab2, col_tab3, col_tab4, col_spacer = st.columns([1, 1, 1.4, 1])

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
    if st.session_state.report_tab == 'weekly':
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


# ===== AI 검색 (RAG) 페이지 =====
elif selected == "🔍 AI 검색":
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

        # ── 단 필터 (검색 범위 선택) ─────────────────────────────────────────
        _rag_all_units = get_all_units()
        _rag_unit_label_map = {"🌐 전체 (모든 단)": None}
        for _ru in _rag_all_units:
            _rag_unit_label_map[f"🏢 {_ru['display_name']}"] = _ru['id']

        # 비관리자는 자기 단을 기본 선택, 관리자는 전체
        if _is_admin or _unit_id is None:
            _rag_default_label = "🌐 전체 (모든 단)"
        else:
            _rag_default_label = next(
                (f"🏢 {_ru['display_name']}" for _ru in _rag_all_units if _ru['id'] == _unit_id),
                "🌐 전체 (모든 단)",
            )

        _rag_unit_labels = list(_rag_unit_label_map.keys())
        _rag_default_idx = _rag_unit_labels.index(_rag_default_label) if _rag_default_label in _rag_unit_labels else 0

        _rag_selected_label = st.selectbox(
            "🏢 검색 범위 (단 필터)",
            _rag_unit_labels,
            index=_rag_default_idx,
            key="rag_unit_filter",
            help="특정 단의 기사만 검색하거나 전체 DB를 대상으로 검색합니다.",
        )
        _rag_unit_id = _rag_unit_label_map[_rag_selected_label]

        with st.form("rag_search_form"):
            query = st.text_area(
                "검색 질문",
                placeholder="예: 지난 한 달간 6G 표준화 관련 주요 동향은?\n예: 국내 기업이 주도한 AI 반도체 소식은?",
                height=100,
            )
            submitted = st.form_submit_button("🔎 검색", use_container_width=True)

        if submitted and query.strip():
            _scope_label = _rag_selected_label.replace("🌐 ", "").replace("🏢 ", "")
            with st.spinner(f"하이브리드 검색 및 답변 생성 중... (범위: {_scope_label})"):
                result = answer_with_rag(query.strip(), top_k=15, days=None, unit_id=_rag_unit_id)

            st.markdown("### 💬 AI 종합 답변")
            st.markdown(result['answer'])

            if result['sources']:
                n_emb = sum(1 for r in result['sources'] if r.get('search_type') == 'embedding')
                n_kw  = sum(1 for r in result['sources'] if r.get('search_type') == 'keyword')
                _scope_desc = _rag_selected_label.replace("🌐 ", "").replace("🏢 ", "")
                st.caption(
                    f"참고 기사 {len(result['sources'])}건 — 임베딩 유사도: {n_emb}건 · 키워드 매칭: {n_kw}건 "
                    f"| 검색 범위: {_scope_desc}"
                )
                st.markdown("### 📰 참고 기사")
                _src_cards = []
                for i, art in enumerate(result['sources'], 1):
                    sim_pct = int(art.get('similarity', 0) * 100)
                    stype = art.get('search_type', 'embedding')
                    badge_color = "#3b82f6" if stype == 'embedding' else "#f59e0b"
                    badge_text  = "🔵 임베딩" if stype == 'embedding' else "🟡 키워드"
                    has_analysis = "📝" if art.get('analysis_result') else "📄"
                    _short_title = art['title'][:70] + ('…' if len(art['title']) > 70 else '')
                    _art_link   = art.get('link', '')
                    _link_tag   = (f'<a href="{_art_link}" target="_blank" '
                                   f'style="color:#005aab;font-size:0.83rem;text-decoration:none;">'
                                   f'🔗 원문</a>' if _art_link else '')
                    _body_raw   = art.get('analysis_result') or art.get('content') or ''
                    _body_label = '분석 요약' if art.get('analysis_result') else '본문 일부'
                    _body_text  = _body_raw[:500] if _body_raw else ''
                    _body_block = (f'<div style="margin-top:8px;font-size:0.85rem;color:#475569;'
                                   f'line-height:1.6;border-top:1px solid #f1f5f9;padding-top:8px;">'
                                   f'<strong>{_body_label}:</strong> {_body_text}</div>'
                                   if _body_text else '')
                    _src_cards.append(f"""
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:13px 16px;
            margin-bottom:8px;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
    <span style="font-size:0.75rem;background:{badge_color};color:white;
                 border-radius:4px;padding:1px 6px;">{badge_text} {sim_pct}%</span>
    <span style="font-size:0.75rem;color:#64748b;">출처: {art['source']}</span>
    <span style="font-size:0.75rem;color:#94a3b8;">{art['published']}</span>
    {_link_tag}
  </div>
  <div style="font-weight:600;color:#1e293b;font-size:0.95rem;line-height:1.5;">
    {has_analysis} [{i}] {_short_title}
  </div>
  {_body_block}
</div>""")
                st.markdown('\n'.join(_src_cards), unsafe_allow_html=True)
        elif submitted:
            st.warning("검색어를 입력해주세요.")

    except ImportError as e:
        st.error(f"RAG 모듈 로드 실패: {e}")
    except Exception as e:
        st.error(f"오류 발생: {e}")


# ===== 트렌드 분석 페이지 =====
elif selected == "📈 트렌드 분석":
    st.markdown('<h1 class="main-header">📈 트렌드 분석 & 표준화 갭</h1>', unsafe_allow_html=True)

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


# ===== 내 설정 페이지 =====
elif selected == "⚙️ 내 설정":
    st.markdown('<h1 class="main-header">👤 내 설정</h1>', unsafe_allow_html=True)
    st.markdown(f"**{_user_name}** ({_user_email}) 님의 설정")
    st.markdown("---")

    current = load_user_settings(_user_email)

    from news_engine import CONFIG, NAVER_QUERIES, RECEIVER_EMAIL

    # ── 내 단 정보 배너 ────────────────────────────────────────────────────────
    if _unit_display_name:
        st.info(f"🏢 소속 단: **{_unit_display_name}** — 아래 키워드·RSS·이메일은 단 전체에 적용됩니다.")
    elif _is_admin:
        st.info("🛠️ 관리자 계정입니다. 단별 RSS/키워드는 각 단 담당자가 설정합니다.")
    else:
        st.warning("⚠️ 소속 단이 배정되지 않았습니다. 관리자(⚙️ 시스템 설정 → 단 멤버십)에게 요청하세요.")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔑 키워드 설정")
        st.caption("네이버 뉴스 검색에 사용할 키워드입니다.")
        default_keywords = current.get('keywords') or NAVER_QUERIES or []
        keywords_input = st.text_area(
            "모니터링할 키워드 (줄바꿈으로 구분)",
            value="\n".join(default_keywords),
            height=180,
            key="user_keywords"
        )

        st.subheader("🤖 AI 모델 선택")
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
        st.subheader("📧 리포트 수신 이메일")
        st.caption("리포트를 받을 이메일 주소입니다. (단 내부 관리용)")
        default_emails = current.get('email_recipients') or (
            [RECEIVER_EMAIL] if RECEIVER_EMAIL else []
        )
        emails_input = st.text_area(
            "수신 이메일 주소 (줄바꿈으로 구분)",
            value="\n".join(default_emails),
            height=120,
            key="user_emails"
        )

        st.subheader("⏰ 자동 실행 설정")
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

    # ── Google Alerts RSS 편집 (단 담당자 + 관리자 모두 편집 가능) ────────────
    st.markdown("---")
    st.subheader("📡 Google Alerts RSS 피드")
    st.caption("Google Alerts에서 생성한 RSS URL을 등록하세요. 단별 수집 시 이 목록을 사용합니다.")

    default_rss = current.get('google_alerts_rss') or []
    rss_input = st.text_area(
        "RSS URL (한 줄에 하나씩)",
        value="\n".join(default_rss),
        height=150,
        key="user_rss",
        placeholder="https://www.google.co.kr/alerts/feeds/...",
    )

    # ── 저장 ──────────────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("💾 설정 저장", type="primary", use_container_width=False, key="save_user_settings_btn"):
        save_user_settings(_user_email, {
            'keywords':          [k.strip() for k in keywords_input.split('\n') if k.strip()],
            'ai_model':          ai_model,
            'email_recipients':  [e.strip() for e in emails_input.split('\n') if e.strip()],
            'schedule_daily':    sched_daily,
            'schedule_weekly':   sched_weekly,
            'google_alerts_rss': [u.strip() for u in rss_input.split('\n') if u.strip()],
        })
        # 단 감지 캐시 초기화 → 다음 리런에서 unit 재로드
        st.session_state.pop("_unit_cache_email", None)
        st.success("✅ 설정이 저장되었습니다.")
        st.rerun()


# ===== 시스템 설정 페이지 (관리자 전용) =====
elif selected == "⚙️ 시스템 설정":
    st.markdown('<h1 class="main-header">⚙️ 시스템 설정</h1>', unsafe_allow_html=True)
    
    cfg = load_config()
    
    # ===== 🔥 커스텀 탭 UI =====
    if 'settings_tab' not in st.session_state:
        st.session_state.settings_tab = 'api'
    
    col_tab1, col_tab2, col_tab3, col_tab4, col_tab5 = st.columns(5)

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

    with col_tab5:
        if st.button("🏢 단 멤버십", key="tab_units_settings", use_container_width=True):
            st.session_state.settings_tab = 'units'
    
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

    elif st.session_state.settings_tab == 'units':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown("### 🏢 단 멤버십 관리")
        st.caption("각 단에 담당자 이메일을 배정합니다. 배정된 계정은 해당 단의 RSS·키워드·이메일을 ⚙️ 내 설정에서 편집할 수 있습니다.")
        st.markdown("---")

        _mgmt_units = get_all_units()
        from sqlalchemy import text as _sa_text

        for _mu in _mgmt_units:
            with st.expander(f"🏢 {_mu['display_name']}  —  {_mu['description']}", expanded=True):
                # 현재 배정된 담당자 목록 조회
                try:
                    with get_db_session() as _ms:
                        _members = _ms.execute(
                            _sa_text("SELECT user_email FROM user_settings "
                                     "WHERE unit_id = :uid ORDER BY user_email"),
                            {"uid": _mu['id']}
                        ).fetchall()
                    _member_emails = [r[0] for r in _members]
                except Exception:
                    _member_emails = []

                if _member_emails:
                    st.markdown(f"**현재 담당자**: {', '.join(_member_emails)}")
                else:
                    st.markdown("**현재 담당자**: *(미배정)*")

                _col_inp, _col_btn = st.columns([3, 1])
                with _col_inp:
                    _new_email = st.text_input(
                        "담당자 이메일 추가/변경 (@tta.or.kr)",
                        placeholder="example@tta.or.kr",
                        key=f"unit_mgmt_email_{_mu['id']}",
                        label_visibility="collapsed",
                    )
                with _col_btn:
                    if st.button("배정", key=f"unit_mgmt_assign_{_mu['id']}", use_container_width=True):
                        _em = _new_email.strip()
                        if not _em:
                            st.warning("이메일을 입력하세요.")
                        elif not _em.endswith("@tta.or.kr"):
                            st.error("@tta.or.kr 계정만 배정 가능합니다.")
                        else:
                            _ok = assign_user_unit(_em, _mu['id'])
                            if _ok:
                                st.session_state.pop("_unit_cache_email", None)
                                st.success(f"✅ {_em} → {_mu['display_name']} 배정 완료")
                                st.rerun()
                            else:
                                st.error("배정 실패. 오류 로그를 확인하세요.")

                # 해제 버튼 (담당자가 있을 때만 표시)
                if _member_emails:
                    with st.expander("담당자 해제", expanded=False):
                        _release_email = st.selectbox(
                            "해제할 담당자",
                            _member_emails,
                            key=f"unit_release_sel_{_mu['id']}",
                        )
                        if st.button(f"🗑️ {_release_email} 해제",
                                     key=f"unit_release_btn_{_mu['id']}",
                                     type="secondary"):
                            _ok2 = assign_user_unit(_release_email, None)
                            if _ok2:
                                st.session_state.pop("_unit_cache_email", None)
                                st.success(f"✅ {_release_email} 단 배정 해제 완료")
                                st.rerun()
                            else:
                                st.error("해제 실패.")

        st.markdown('</div>', unsafe_allow_html=True)
