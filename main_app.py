"""
IRONAGE AI Analytics System v5.0
Streamlit 웹 대시보드 - 완전판 (수정 버전)
"""

import os
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

# ── KST 타임존 헬퍼 ────────────────────────────────────────
import pytz as _pytz
_KST = _pytz.timezone('Asia/Seoul')

def _kst_now():
    return datetime.now(tz=_KST)

def _to_kst_str(dt_or_str, fmt='%Y-%m-%d'):
    if not dt_or_str:
        return ''
    try:
        s = str(dt_or_str).replace('T', ' ')[:19]
        try:
            dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.strptime(s[:10], '%Y-%m-%d')
        dt = _pytz.utc.localize(dt)
        return dt.astimezone(_KST).strftime(fmt)
    except Exception:
        return str(dt_or_str)[:10]


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
        run_all_units_daily,
        log_user_activity,
        get_activity_logs,
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

# ===== 인증 (패스워드 + 이메일 기반) =====
# secrets에 APP_PASSWORD 설정 시 로그인 화면 표시.
# 미설정 시 로컬 개발 모드로 자동 폴백.
# 관리자: ADMIN_PASSWORD (별도) 또는 ADMIN_EMAILS 목록과 일치.

_AUTH_PASSWORD  = st.secrets.get("APP_PASSWORD", "")   # 일반 접속 비밀번호
_ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", _AUTH_PASSWORD)  # 관리자 비밀번호

# 로그인 상태 확인
_logged_in   = st.session_state.get("_logged_in", False)
_user_email  = st.session_state.get("_user_email", "")

if _AUTH_PASSWORD and not _logged_in:
    # ── 로그인 화면 ──────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .login-box { max-width: 400px; margin: 80px auto; padding: 2rem;
                 background: #1e1e2e; border-radius: 12px;
                 box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
    </style>
    """, unsafe_allow_html=True)

    _lc1, _lc2, _lc3 = st.columns([1, 2, 1])
    with _lc2:
        st.markdown("## 🔐 IRONAGE AI Analytics")
        st.markdown("##### TTA ICT 뉴스 인텔리전스 시스템")
        st.markdown("---")
        _inp_email = st.text_input(
            "이메일 (예: hong@tta.or.kr)",
            placeholder="yourname@tta.or.kr",
            key="_login_email",
        )
        _inp_pw = st.text_input(
            "접속 비밀번호",
            type="password",
            key="_login_pw",
        )
        if st.button("🔑 로그인", use_container_width=True, type="primary"):
            # 이메일 도메인 검사 (비어 있으면 로컬 계정으로 처리)
            _email_ok = (
                _inp_email.strip().endswith("@tta.or.kr")
                or _inp_email.strip() == ""
            )
            _pw_ok = _inp_pw in (_AUTH_PASSWORD, _ADMIN_PASSWORD)
            if _pw_ok and _email_ok:
                _final_email = _inp_email.strip() or "local@tta.or.kr"
                st.session_state["_logged_in"]  = True
                st.session_state["_user_email"] = _final_email
                # 관리자 비밀번호로 로그인하거나 관리자 이메일이면 admin 플래그 설정
                st.session_state["_session_is_admin"] = (
                    _inp_pw == _ADMIN_PASSWORD or
                    _final_email in {"ironage@tta.or.kr", "local@tta.or.kr"}
                )
                # 접속 시작 시각 저장 (로그아웃 시 세션 시간 계산용)
                import time as _time
                st.session_state["_login_at"] = _time.time()
                # 접속 로그 기록
                try:
                    log_user_activity(_final_email, 'login', {
                        'is_admin': st.session_state["_session_is_admin"]
                    })
                except Exception:
                    pass
                st.rerun()
            elif not _email_ok:
                st.error("❌ @tta.or.kr 이메일 주소만 접속 가능합니다.")
            else:
                st.error("❌ 비밀번호가 올바르지 않습니다.")
        st.caption("@tta.or.kr 계정만 접속 가능합니다.")
    st.stop()

# 인증 완료 또는 로컬 모드
if not _user_email:
    # 로컬 개발 모드 (APP_PASSWORD 미설정) 또는 세션 만료 복구
    _user_email = "local@tta.or.kr"
    st.session_state["_user_email"] = _user_email

_user_name = _user_email.split("@")[0]

# 관리자 판정 — 이메일 목록 일치 OR 로그인 시 관리자 비밀번호 사용
_ADMIN_EMAILS = {"ironage@tta.or.kr", "local@tta.or.kr"}
_is_admin = (
    _user_email in _ADMIN_EMAILS
    or st.session_state.get("_session_is_admin", False)
)

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

    /* ═══════════════════════════════════════════════════
       사이드바 — 전체 재설계
       ═══════════════════════════════════════════════════ */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e2d4f 0%, #162040 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.08) !important;
    }

    /* 사이드바 내 모든 텍스트 기본색 */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }

    /* 헤딩 */
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #ffffff !important;
        letter-spacing: -0.02em !important;
    }

    /* 캡션·소문자 */
    section[data-testid="stSidebar"] .stCaption,
    section[data-testid="stSidebar"] small,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #94a3b8 !important;
        font-size: 0.82rem !important;
    }

    /* 구분선 */
    section[data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.12) !important;
        margin: 0.6rem 0 !important;
    }

    /* 로그아웃·일반 버튼 */
    section[data-testid="stSidebar"] .stButton > button {
        background: rgba(255,255,255,0.08) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 8px !important;
        font-size: 0.88rem !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255,255,255,0.16) !important;
        color: #ffffff !important;
    }

    /* 셀렉트박스 — 테스트 유저 전환 */
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.18) !important;
        border-radius: 8px !important;
        color: #e2e8f0 !important;
    }
    section[data-testid="stSidebar"] .stSelectbox svg {
        fill: #94a3b8 !important;
    }

    /* ── 메뉴 라디오 버튼 ── */
    section[data-testid="stSidebar"] .stRadio > div {
        gap: 2px !important;
    }
    section[data-testid="stSidebar"] .stRadio > div > label {
        display: flex !important;
        align-items: center !important;
        padding: 9px 14px !important;
        border-radius: 8px !important;
        color: #cbd5e1 !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        transition: background 0.15s, color 0.15s, border-left 0.15s !important;
        width: 100% !important;
        border-left: 3px solid transparent !important;
        margin-bottom: 2px !important;
    }
    section[data-testid="stSidebar"] .stRadio > div > label:hover {
        background: rgba(255,255,255,0.09) !important;
        color: #ffffff !important;
        border-left-color: rgba(0,90,171,0.6) !important;
    }
    /* 선택된 메뉴 항목 — 파란 좌측 바 + 배경 강조 */
    section[data-testid="stSidebar"] .stRadio > div > label[data-checked="true"],
    section[data-testid="stSidebar"] .stRadio input[type="radio"]:checked ~ div label {
        background: rgba(0, 90, 171, 0.30) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border-left: 3px solid #4da6ff !important;
    }
    /* 라디오 원형 버튼 숨김 */
    section[data-testid="stSidebar"] .stRadio input[type="radio"] {
        display: none !important;
    }
    /* 라디오 div wrapper — 배경 없애기 */
    section[data-testid="stSidebar"] .stRadio > div > label > div:first-child {
        display: none !important;
    }

    /* 메뉴 섹션 레이블 ("메뉴" 텍스트) */
    section[data-testid="stSidebar"] .stMarkdown strong {
        color: #94a3b8 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
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
    """설정 로드.
    우선순위: ① Streamlit Secrets (환경변수) → ② data/config.json → ③ 하드코딩 기본값
    Streamlit Cloud는 파일시스템이 재시작마다 초기화되므로 Secrets가 최우선.
    """
    # ① Streamlit Secrets / 환경변수 기반 기본값
    base = {
        'ai_model': 'openai',
        'openai_api_key': OPENAI_API_KEY,
        'claude_api_key': os.environ.get('CLAUDE_API_KEY', ''),
        'gemini_api_key': os.environ.get('GEMINI_API_KEY', ''),
        'perplexity_api_key': os.environ.get('PERPLEXITY_API_KEY', ''),
        'naver_client_id': NAVER_CLIENT_ID,
        'naver_client_secret': NAVER_CLIENT_SECRET,
        'gmail_sender': SENDER_EMAIL,
        'gmail_password': GMAIL_PASSWORD,
        'gmail_receivers': RECEIVER_EMAIL,
        'google_alerts_rss': GOOGLE_ALERTS_RSS_URLS,
        'naver_queries': NAVER_QUERIES,
        'schedule_daily': '09:00',
        'schedule_weekly': 'Monday 09:00',
        'schedule_monthly': '1 09:00',
    }
    # ② data/config.json이 있으면 덮어쓰기 (로컬 커스텀 설정)
    # 단, API 키가 비어 있으면 Secrets 값 유지
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for k, v in saved.items():
                # API 키 항목은 비어있으면 Secrets 값 우선
                if k.endswith('_key') or k.endswith('_id') or k.endswith('_secret'):
                    if v:
                        base[k] = v
                else:
                    base[k] = v
        except Exception:
            pass
    return base


def save_config(cfg):
    """설정 저장 — 파일 + news_engine.CONFIG 인메모리 딕셔너리 동시 반영"""
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    # ★ news_engine.CONFIG 인메모리 딕셔너리를 즉시 업데이트
    # (모듈 로드 시 한 번만 읽히므로, 파일 저장만으로는 현재 세션에 반영 안 됨)
    try:
        import news_engine as _ne
        _ne.CONFIG.update(cfg)
    except Exception:
        pass  # 임포트 실패 시 무시 — 다음 재시작에 반영됨

    # 클라이언트 캐시 초기화 (새 API 키로 재생성 유도)
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
        st.caption("🛠️ 시스템 설정은 관리자 전용입니다.")
    else:
        st.caption("⚠️ 단 미배정")
    # 로그아웃 버튼 — APP_PASSWORD 설정 시(= 인증 모드)에만 표시
    if st.secrets.get("APP_PASSWORD", ""):
        if st.button("🚪 로그아웃", use_container_width=True, key="sidebar_logout"):
            try:
                import time as _time
                _login_at  = st.session_state.get("_login_at")
                _duration  = int(_time.time() - _login_at) if _login_at else None
                _dur_str   = (
                    f"{_duration // 3600}시간 {(_duration % 3600) // 60}분 {_duration % 60}초"
                    if _duration is not None else "알 수 없음"
                )
                log_user_activity(_user_email, 'logout', {
                    'session_seconds': _duration,
                    'session_duration': _dur_str,
                })
            except Exception:
                pass
            st.session_state.clear()
            st.rerun()
    st.markdown("---")

    # ── 🧪 테스트 유저 전환 (로컬 모드 전용 — APP_PASSWORD 미설정 시) ─────────
    if not st.secrets.get("APP_PASSWORD", ""):
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
        _cur_email = st.session_state.get("_user_email", "local@tta.or.kr")
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
            st.session_state["_user_email"] = _sel_email
            st.rerun()
        st.markdown("---")
    # ─────────────────────────────────────────────────────────────────────────

    _user_options = ["🏠 홈", "📰 뉴스 현황", "🔍 AI 검색", "📊 인텔리전스", "⚙️ 단별 설정"]
    _admin_options = ["⚙️ 시스템 설정"]

    _all_options = _user_options + (_admin_options if _is_admin else [])

    st.markdown("**메뉴**")
    selected = st.radio(
        "nav",
        options=_all_options,
        label_visibility="collapsed",
        key="main_nav",
    )

    if _is_admin:
        st.caption("🛠️ 시스템 설정은 관리자 전용입니다.")

    st.markdown("---")
    st.markdown("**한국정보통신기술협회(TTA)**")
    st.markdown(f"*{_kst_now().strftime('%Y-%m-%d %H:%M')} KST*")


# ===== 홈 페이지 헬퍼 =====
def _render_article_card(art: dict) -> str:
    """단일 기사 HTML 카드 반환."""
    try:
        data = json.loads(art.get('analysis_result') or '{}')
    except Exception:
        data = {}
    title    = art.get('title', '제목 없음')
    source   = art.get('source', '')
    raw_main = data.get('main_content', '') or ''
    summary  = (raw_main[:300] + '…') if len(raw_main) > 300 else raw_main
    link     = art.get('link', '')
    date_str = _to_kst_str(art.get('collected_at', ''))
    impact   = data.get('impact_level', '')
    impact_color = {'Critical': '#dc2626', 'High': '#ea580c',
                    'Medium': '#2563eb', 'Low': '#64748b'}.get(impact, '#64748b')
    impact_badge = (f'<span style="background:{impact_color};color:#fff;'
                    f'font-size:0.7rem;padding:1px 7px;border-radius:99px;'
                    f'font-weight:600;">{impact}</span> ') if impact else ''
    link_tag = (f'<a href="{link}" target="_blank" '
                f'style="color:#005aab;text-decoration:none;font-size:0.82rem;">🔗 원문</a>'
                if link else '')
    # 키워드 뱃지
    kw_raw = data.get('keywords', []) or []
    if isinstance(kw_raw, str):
        try:
            kw_raw = json.loads(kw_raw)
        except Exception:
            kw_raw = [k.strip() for k in kw_raw.split(',') if k.strip()]
    kw_badges = ''.join(
        f'<span style="background:#f0f4ff;color:#3b5bdb;font-size:0.72rem;'
        f'padding:1px 7px;border-radius:99px;margin:2px;display:inline-block;">'
        f'{k}</span>'
        for k in kw_raw[:6]
    )
    kw_block = f'<div style="margin-top:6px;">{kw_badges}</div>' if kw_badges else ''
    return f"""
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;
            margin-bottom:10px;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
  <div style="font-size:0.76rem;font-weight:700;color:#005aab;
              margin-bottom:4px;">[{source}] {impact_badge}</div>
  <div style="font-weight:600;color:#1e293b;font-size:0.96rem;
              line-height:1.5;margin-bottom:7px;">{title}</div>
  <div style="font-size:0.87rem;color:#475569;line-height:1.65;
              margin-bottom:9px;">{summary}</div>
  {kw_block}
  <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:8px;">
    {link_tag}
    <span style="color:#94a3b8;font-size:0.76rem;">수집: {date_str}</span>
  </div>
</div>"""


def _render_unit_articles_by_date(articles: list, unit_display: str, tab_key: str):
    """단별 기사를 일자별로 나눠 최대 20개 렌더링한다."""
    analyzed = [a for a in articles if a.get('is_analyzed')]
    if not analyzed:
        st.info(f"**{unit_display}** 분석 기사가 없습니다.\n\n"
                "관리자에게 뉴스 수집/분석 실행을 요청하세요.")
        return

    # 일자별 그룹핑 (KST 날짜 기준)
    from collections import defaultdict as _ddict
    _by_date = _ddict(list)
    for a in analyzed:
        _d = _to_kst_str(a.get('collected_at', ''), fmt='%Y-%m-%d')
        _by_date[_d].append(a)

    # 날짜 내림차순 정렬
    _dates = sorted(_by_date.keys(), reverse=True)

    # 날짜 선택
    _date_labels = [f"{d} ({len(_by_date[d])}건)" for d in _dates]
    _sel_label = st.selectbox(
        "📅 날짜 선택",
        _date_labels,
        index=0,
        key=f"date_sel_{tab_key}",
    )
    _sel_date = _dates[_date_labels.index(_sel_label)]
    _day_arts = _by_date[_sel_date][:20]  # 최대 20개

    st.caption(f"**{_sel_date}** 분석 기사 {len(_day_arts)}건 / 전체 {len(_by_date[_sel_date])}건")
    cards = [_render_article_card(a) for a in _day_arts]
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
    _hc2.metric("분석 완료", _hs['analyzed'])
    _hc3.metric("전체 기사", _hs['total'])
    _hc4.metric("대기 중", _hs['pending'])

    # ── 전체 프로세스 실행 (관리자 전용) ──────────────────────────────────────
    if _is_admin:
        st.markdown("---")
        with st.expander("🚀 전체 프로세스 실행 (관리자 전용)", expanded=False):
            _home_cfg = load_config()
            _home_model = _home_cfg.get('ai_model', 'openai')

            st.markdown(f"""
각 단의 키워드·RSS로 **단별 독립 수집→AI분석→이메일**을 순차 실행합니다.

| 단계 | 내용 |
|------|------|
| 1 | 단별 키워드·RSS로 뉴스 수집 (키워드 혼합 없음) |
| 2 | AI 선별 (중요도 상위 50개) |
| 3 | 심층 분석 (최대 20건) |
| 4 | Google Docs 리포트 생성 |
| 5 | 단별 수신자 이메일 발송 |
| 6 | 주간 엑셀 누적 저장 |

🤖 **AI 모델:** `{_home_model.upper()}` &nbsp;|&nbsp; ⏱️ **예상 소요:** 단당 10~20분
""")
            # 미설정 단 경고
            _all_u = get_all_units()
            _skip_units = [
                u['display_name'] for u in _all_u
                if not load_unit_settings(u['id']).get('keywords')
                and not load_unit_settings(u['id']).get('google_alerts_rss')
            ]
            if _skip_units:
                st.warning(f"⚠️ 키워드/RSS 미설정으로 건너뛸 단: **{', '.join(_skip_units)}**\n\n⚙️ 단별 설정에서 키워드를 추가하세요.")

            if st.button("🚀 4개 단 전체 프로세스 시작", type="primary",
                         use_container_width=True, key="home_full_process_start"):
                _home_status = st.empty()
                _home_status.info("⏳ 실행 중... 단별로 순차 처리합니다. 완료까지 수분~수십분 소요될 수 있습니다.")
                try:
                    log_user_activity(_user_email, 'daily_run', {'model': _home_model})
                    _summary = run_all_units_daily(ai_model=_home_model)
                    _home_status.empty()

                    st.success("🎉 전체 프로세스 완료!")
                    for _uname, _r in _summary.items():
                        if _r.get('errors') and not _r.get('analyzed'):
                            st.warning(f"⚠️ [{_uname}] 건너뜀 — {_r['errors'][0]}")
                        else:
                            st.success(
                                f"✅ [{_uname}] 수집 {_r['collected']}건 / "
                                f"저장 {_r['saved']}건 / 분석 {_r['analyzed']}건"
                            )
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
                # 단별 최근 30일 기사 로드 (일자별 선택 가능하도록 충분히)
                if _unit.get('name') == 'radio_network':
                    _unit_news = load_news_from_db(days=30, unit_id=_unit['id'])
                    _legacy = load_news_from_db(days=30, unit_id=-1)
                    _seen_lnk = {a['link'] for a in _unit_news}
                    for _la in _legacy:
                        if _la['link'] not in _seen_lnk:
                            _unit_news.append(_la)
                            _seen_lnk.add(_la['link'])
                else:
                    _unit_news = load_news_from_db(days=30, unit_id=_unit['id'])
                _analyzed_count = sum(1 for a in _unit_news if a.get('is_analyzed'))

                # 단 설명 + 키워드 현황 + 기사 수 통계
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
                        st.caption("⚠️ 키워드 미설정 — ⚙️ 단별 설정에서 단 키워드를 추가하세요.")
                with _col_cnt:
                    st.metric(
                        label="수집/분석",
                        value=f"{len(_unit_news)}건",
                        delta=f"분석 {_analyzed_count}건",
                        delta_color="normal",
                        help="최근 30일 기준"
                    )

                # ── 관리자 전용: 이 단만 수집·분석 실행 ──────────────────
                if _is_admin:
                    with st.expander(
                        f"🚀 [{_unit['display_name']}] 수집·분석 실행 (관리자)",
                        expanded=False
                    ):
                        _ucol1, _ucol2 = st.columns([2, 1])
                        with _ucol1:
                            _unit_model_opts = ["gemini-2.5-flash", "gpt-4o",
                                                "claude-sonnet-4-6", "sonar-pro"]
                            _unit_run_model = st.selectbox(
                                "AI 모델", _unit_model_opts,
                                key=f"unit_model_{_unit['id']}"
                            )
                        with _ucol2:
                            st.markdown("<div style='margin-top:28px'></div>",
                                        unsafe_allow_html=True)
                            _run_unit_btn = st.button(
                                "▶ 지금 실행",
                                key=f"run_unit_{_unit['id']}",
                                type="primary",
                                use_container_width=True
                            )

                        if _run_unit_btn:
                            if not _unit_kws and not _unit_cfg.get('rss_urls'):
                                st.warning(
                                    "⚠️ 이 단의 키워드·RSS가 설정되지 않아 실행할 수 없습니다. "
                                    "⚙️ 단별 설정에서 먼저 키워드를 추가하세요."
                                )
                            else:
                                _unit_status = st.empty()
                                _unit_status.info(
                                    f"⏳ [{_unit['display_name']}] 수집·분석 중…"
                                )
                                try:
                                    # run_all_units_daily를 이 단 ID만 target으로 실행
                                    _u_summary = run_all_units_daily(
                                        ai_model=_unit_run_model,
                                        target_unit_id=_unit['id']
                                    )
                                    _unit_status.empty()
                                    _ur = _u_summary.get(
                                        _unit['display_name'],
                                        _u_summary.get(list(_u_summary.keys())[0], {})
                                        if _u_summary else {}
                                    )
                                    if _ur.get('errors') and not _ur.get('analyzed'):
                                        st.error(
                                            f"❌ 오류: {_ur['errors'][0]}"
                                        )
                                    else:
                                        st.success(
                                            f"✅ 완료! 수집 {_ur.get('collected', 0)}건 / "
                                            f"저장 {_ur.get('saved', 0)}건 / "
                                            f"분석 {_ur.get('analyzed', 0)}건"
                                        )
                                        st.rerun()
                                except Exception as _ue:
                                    _unit_status.empty()
                                    st.error(f"❌ 오류: {str(_ue)}")

                _render_unit_articles_by_date(
                    _unit_news, _unit['display_name'], tab_key=f"u{_unit['id']}"
                )


# ===== 📰 뉴스 현황 페이지 =====
elif selected == "📰 뉴스 현황":
    from itertools import groupby as _nv_groupby

    st.markdown('<h1 class="main-header">📰 뉴스 파이프라인 현황</h1>', unsafe_allow_html=True)
    st.markdown("수집 → 선별 → 분석 각 단계의 기사를 한눈에 확인합니다.")
    st.markdown("---")

    # ── 필터 행 ──────────────────────────────────────────────────────────────────
    # ── 필터 행 ──────────────────────────────────────────────────────────────────
    _nv_f1, _nv_f2, _nv_f3 = st.columns([2, 2, 3])
    with _nv_f1:
        _nv_days = st.slider("조회 기간 (최근 N일)", 1, 30, 7, key="nv_days")
    with _nv_f2:
        _nv_units      = get_all_units()
        _nv_unit_opts  = {"전체": None} | {u['display_name']: u['id'] for u in _nv_units}
        _nv_unit_label = st.selectbox("단 필터", list(_nv_unit_opts.keys()), key="nv_unit")
        _nv_unit_id    = _nv_unit_opts[_nv_unit_label]
    with _nv_f3:
        _nv_search = st.text_input(
            "🔍 키워드 검색", placeholder="제목·출처·키워드 검색…", key="nv_search"
        )

    # ── 데이터 로드 ───────────────────────────────────────────────────────────────
    _nv_all = load_news_from_db(days=_nv_days, unit_id=_nv_unit_id)

    if not _nv_all:
        st.info("해당 기간에 수집된 기사가 없습니다.")
    else:
        import datetime as _nv_dt
        import html as _html_mod

        _DAYS_KR = ['월', '화', '수', '목', '금', '토', '일']

        # ── 날짜별 건수 집계 (최근순) ─────────────────────────────────────────
        _nv_date_counts: dict = {}
        for _a in _nv_all:
            _d = (_a.get('collected_at') or '')[:10]
            if _d:
                _nv_date_counts[_d] = _nv_date_counts.get(_d, 0) + 1

        _nv_dates_sorted = sorted(_nv_date_counts.keys(), reverse=True)

        def _nv_date_label(d):
            try:
                _obj = _nv_dt.date.fromisoformat(d)
                _dow = _DAYS_KR[_obj.weekday()]
                return f"{d[5:]} ({_dow})  {_nv_date_counts[d]}건"
            except Exception:
                return d

        _nv_date_labels  = [_nv_date_label(d) for d in _nv_dates_sorted]
        _nv_label_to_date = {_nv_date_label(d): d for d in _nv_dates_sorted}

        # ── 날짜 선택 (라디오, 최근순) ────────────────────────────────────────
        _nv_picked_label = st.radio(
            "📅 날짜 선택",
            _nv_date_labels,
            horizontal=True,
            key="nv_date_radio",
        )
        _nv_picked_date = _nv_label_to_date.get(_nv_picked_label, _nv_dates_sorted[0])

        st.markdown("---")

        # ── 선택 날짜 기사만 ─────────────────────────────────────────────────
        _nv_day_all = [
            a for a in _nv_all
            if (a.get('collected_at') or '')[:10] == _nv_picked_date
        ]

        # ── 파이프라인 요약 지표 (선택 날짜 기준) ─────────────────────────────
        _nv_day_sel = [a for a in _nv_day_all if (a.get('quality_score') or 0) > 0.5]
        _nv_day_ana = [a for a in _nv_day_all if a.get('is_analyzed')]

        _nv_m1, _nv_m2, _nv_m3, _nv_m4 = st.columns(4)
        _nv_m1.metric("📥 수집됨", f"{len(_nv_day_all):,}건")
        _nv_m2.metric(
            "✅ 선별됨",
            f"{len(_nv_day_sel):,}건",
            delta=f"{len(_nv_day_sel)/len(_nv_day_all)*100:.0f}%" if _nv_day_all else "0%",
        )
        _nv_m3.metric(
            "🔬 분석됨",
            f"{len(_nv_day_ana):,}건",
            delta=f"{len(_nv_day_ana)/len(_nv_day_all)*100:.0f}%" if _nv_day_all else "0%",
        )
        _nv_m4.metric(
            "📊 분석률",
            f"{len(_nv_day_ana)/len(_nv_day_sel)*100:.0f}%" if _nv_day_sel else "0%",
            help="선별된 기사 중 실제 분석 완료 비율",
        )
        st.markdown("---")

        # ── 키워드 검색 필터 (None-safe) ──────────────────────────────────────
        def _nv_match(a, kw):
            if not kw:
                return True
            kw_l = kw.lower()
            if kw_l in (a.get('title')  or '').lower(): return True
            if kw_l in (a.get('source') or '').lower(): return True
            try:
                return any(kw_l in str(k).lower()
                           for k in json.loads(a.get('extracted_keywords') or '[]'))
            except Exception:
                return False

        _nv_filtered = [a for a in _nv_day_all if _nv_match(a, _nv_search)]
        # 시간 내림차순 정렬
        _nv_filtered.sort(key=lambda x: x.get('collected_at') or '', reverse=True)

        # ── 상태 배지 색 ────────────────────────────────────────────────────
        def _nv_badge(a):
            if a.get('is_analyzed'):
                return '🔬 분석완료', '#1976D2'
            if (a.get('quality_score') or 0) > 0.5:
                return '✅ 선별됨',   '#388E3C'
            return '📥 수집됨',       '#757575'

        # ── 카드 HTML 생성 함수 (AI 검색 결과 스타일) ────────────────────────
        def _nv_card(a):
            title  = (a.get('title')  or '제목 없음')
            url    = a.get('link')    or '#'
            src    = a.get('source')  or ''
            dt     = (a.get('collected_at') or '')[:16]
            unit   = get_unit_display_name(a['unit_id']) if a['unit_id'] else '미분류'
            score  = a.get('quality_score') or 0
            lbl, bc = _nv_badge(a)
            pct    = int(score * 100)

            title_color  = '#1565C0' if a.get('is_analyzed') else '#1e293b'
            title_weight = '700'     if a.get('is_analyzed') else '600'

            # 분석 본문 (요약 250자 + 전체 보기 토글)
            body_block = ''
            if a.get('is_analyzed'):
                raw = (a.get('analysis_result') or '').strip()
                if raw:
                    snippet   = raw[:250] + ('…' if len(raw) > 250 else '')
                    full_html = _html_mod.escape(raw).replace('\n', '<br>')
                    toggle_block = ''
                    if len(raw) > 250:
                        toggle_block = (
                            f'<details style="margin-top:5px;">'
                            f'<summary style="cursor:pointer;font-size:0.81rem;'
                            f'color:#1976D2;padding:3px 0;user-select:none;'
                            f'list-style:none;outline:none;">'
                            f'▶ 분석 내용 전체 보기</summary>'
                            f'<div style="margin-top:8px;font-size:0.84rem;color:#334155;'
                            f'line-height:1.75;border-top:1px solid #e2e8f0;'
                            f'padding-top:8px;">{full_html}</div>'
                            f'</details>'
                        )
                    body_block = (
                        f'<div style="margin-top:8px;font-size:0.84rem;color:#475569;'
                        f'line-height:1.6;border-top:1px solid #f1f5f9;padding-top:7px;">'
                        f'{snippet}</div>'
                        f'{toggle_block}'
                    )

            # 품질 점수 바
            score_bar = (
                f'<div style="display:inline-flex;align-items:center;gap:3px;vertical-align:middle;">'
                f'<div style="background:#e0e0e0;border-radius:3px;width:36px;height:7px;">'
                f'<div style="background:#42A5F5;width:{pct}%;height:100%;border-radius:3px;"></div>'
                f'</div>'
                f'<span style="font-size:11px;color:#94a3b8;">{score:.2f}</span>'
                f'</div>'
            )

            return f"""
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:13px 16px;
            margin-bottom:8px;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
    <span style="font-size:0.75rem;background:{bc};color:#fff;
                 border-radius:4px;padding:2px 7px;">{lbl}</span>
    <span style="font-size:0.75rem;color:#64748b;">출처: {src}</span>
    <span style="font-size:0.75rem;color:#64748b;">단: {unit}</span>
    <span style="font-size:0.75rem;color:#94a3b8;">{dt}</span>
    {score_bar}
    <a href="{url}" target="_blank"
       style="color:#005aab;font-size:0.82rem;text-decoration:none;margin-left:auto;">
       🔗 원문</a>
  </div>
  <div style="font-weight:{title_weight};color:{title_color};font-size:0.95rem;line-height:1.5;">
    <a href="{url}" target="_blank" style="color:{title_color};text-decoration:none;">{title}</a>
  </div>
  {body_block}
</div>"""

        # ── 카드 렌더링 ───────────────────────────────────────────────────────
        _nv_kw_note = f'  검색어: **"{_nv_search}"** ·' if _nv_search else ''
        _cnt_a = sum(1 for a in _nv_filtered if a.get('is_analyzed'))
        _cnt_s = sum(1 for a in _nv_filtered
                     if not a.get('is_analyzed') and (a.get('quality_score') or 0) > 0.5)
        _cnt_r = len(_nv_filtered) - _cnt_a - _cnt_s

        if not _nv_filtered:
            st.info("검색 조건에 맞는 기사가 없습니다." if _nv_search else "해당 날짜에 기사가 없습니다.")
        else:
            st.caption(
                f"{_nv_kw_note} **{len(_nv_filtered):,}건**"
                f"  |  🔬 분석완료 {_cnt_a}건  ·  ✅ 선별됨 {_cnt_s}건  ·  📥 수집됨 {_cnt_r}건"
            )
            st.markdown(
                '\n'.join(_nv_card(a) for a in _nv_filtered),
                unsafe_allow_html=True,
            )


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
            log_user_activity(_user_email, 'rag_search', {
                'query': query.strip()[:100], 'scope': _scope_label
            })
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


# ===== 📊 인텔리전스 대시보드 페이지 =====
elif selected == "📊 인텔리전스":
    st.markdown('<h1 class="main-header">📊 인텔리전스 대시보드</h1>', unsafe_allow_html=True)
    st.markdown("키워드 트렌드 · 영향도 히트맵 · 급등 알림을 종합 분석합니다.")
    st.markdown("---")

    if _INTEL_WIDGET_OK:
        render_keyword_intelligence("intel_page")
    else:
        st.warning("⚠️ intelligence_widgets.py 모듈을 불러오지 못했습니다.")
        st.info("프로젝트 폴더에 `intelligence_widgets.py` 파일이 있는지 확인하세요.")

    st.markdown("---")
    # ── 엑셀 리포트 다운로드 ──────────────────────────────────────────────────
    st.markdown("### 📥 엑셀 리포트 다운로드")
    st.caption(
        "저장 위치: `data/reports/` — 뉴스 분석 (`news_analysis_YYYY_WNN.xlsx`)"
        " / 키워드 통계 (`keyword_summary_YYYY_WNN.xlsx`)"
    )
    _rpt_dir = Path("data/reports")
    _rpt_dir.mkdir(parents=True, exist_ok=True)
    _xlsx_files = sorted(_rpt_dir.glob("*.xlsx"), reverse=True)
    if _xlsx_files:
        _dl_col1, _dl_col2 = st.columns(2)
        _news_files = [f for f in _xlsx_files if f.name.startswith("news_analysis")]
        _kw_files   = [f for f in _xlsx_files if f.name.startswith("keyword_summary")]

        with _dl_col1:
            st.markdown("**📊 뉴스 분석 엑셀**")
            for _xf in _news_files[:5]:
                with open(_xf, "rb") as _fh:
                    st.download_button(
                        label=f"⬇️ {_xf.name}",
                        data=_fh.read(),
                        file_name=_xf.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_news_{_xf.stem}",
                    )
        with _dl_col2:
            st.markdown("**🔑 키워드 통계 엑셀**")
            for _xf in _kw_files[:5]:
                with open(_xf, "rb") as _fh:
                    st.download_button(
                        label=f"⬇️ {_xf.name}",
                        data=_fh.read(),
                        file_name=_xf.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_kw_{_xf.stem}",
                    )
    else:
        st.info("아직 생성된 엑셀 파일이 없습니다. 전체 프로세스를 실행하면 자동 저장됩니다.")


# ===== 내 설정 페이지 =====
elif selected == "⚙️ 단별 설정":
    st.markdown('<h1 class="main-header">⚙️ 단 설정 관리</h1>', unsafe_allow_html=True)

    _set_all_units = get_all_units()

    if not _set_all_units:
        st.error("단 정보를 불러올 수 없습니다. DB 연결을 확인하세요.")
    else:
        if _is_admin:
            st.info("🛠️ 관리자 모드 — 모든 단의 키워드·이메일·RSS를 관리합니다.")
            _set_tabs = st.tabs([f"🏢 {u['display_name']}" for u in _set_all_units])
            _set_units = _set_all_units
        elif _unit_id is not None:
            _my_unit = next((u for u in _set_all_units if u['id'] == _unit_id), None)
            if not _my_unit:
                st.warning("소속 단 정보를 찾을 수 없습니다.")
                _set_tabs = []
                _set_units = []
            else:
                st.info(f"🏢 소속 단: **{_unit_display_name}** 의 수집 설정을 관리합니다.")
                _set_tabs = [None]
                _set_units = [_my_unit]
        else:
            st.warning("⚠️ 소속 단이 배정되지 않았습니다. 관리자(⚙️ 시스템 설정 → 단 멤버십)에게 요청하세요.")
            _set_tabs = []
            _set_units = []

        def _do_unit_settings_panel(unit):
            u_cfg = load_unit_settings(unit['id'])
            uid = unit['id']
            _desc = unit.get('description', '')
            if _desc:
                st.caption(f"📋 {_desc}")
            _sc1, _sc2 = st.columns(2)
            with _sc1:
                st.subheader("🔑 모니터링 키워드")
                st.caption("네이버 뉴스 검색 키워드 (줄바꿈으로 구분)")
                _kw_in = st.text_area(
                    "키워드", label_visibility="collapsed", height=200,
                    value="\n".join(u_cfg.get("keywords") or []),
                    key=f"s_kw_{uid}"
                )
                st.subheader("📡 Google Alerts RSS")
                st.caption("RSS URL (줄바꿈으로 구분)")
                _rss_in = st.text_area(
                    "RSS", label_visibility="collapsed", height=130,
                    value="\n".join(u_cfg.get("google_alerts_rss") or []),
                    key=f"s_rss_{uid}",
                    placeholder="https://www.google.co.kr/alerts/feeds/..."
                )
            with _sc2:
                st.subheader("📧 이메일 발송 설정")

                # ── 실제 발송 제목 미리보기 (읽기 전용) ──────────────
                from news_engine import _UNIT_EMAIL_SUBJECT_MAP
                import datetime, pytz as _pytz
                _kst_tz     = _pytz.timezone('Asia/Seoul')
                _today_str  = datetime.datetime.now(_kst_tz).strftime('%Y년 %m월 %d일')
                _subj_body  = _UNIT_EMAIL_SUBJECT_MAP.get(
                    unit.get('name', ''),
                    f"{unit['display_name']} 동향 보고서"
                )
                _preview_subject = f"[TTA] {_subj_body} ({_today_str})"
                st.markdown(
                    "**✉️ 실제 발송되는 이메일 제목**",
                )
                st.code(_preview_subject, language=None)

                # ── 발신자 표시명 ─────────────────────────────────────
                st.caption("📤 발신자 표시명")
                _sender_in = st.text_input(
                    "발신자명", label_visibility="collapsed",
                    value=u_cfg.get("sender_name") or "",
                    key=f"s_sname_{uid}",
                    placeholder=f"{unit['display_name']} AI뉴스봇"
                )
                st.caption(
                    "수신자에게 보이는 보내는 사람 이름입니다. "
                    f"비워두면 '{unit['display_name']} AI'로 자동 설정됩니다."
                )

                # ── 수신자 목록 ───────────────────────────────────────
                st.caption("📥 수신자 이메일 목록 (줄바꿈으로 구분)")
                _email_in = st.text_area(
                    "이메일", label_visibility="collapsed", height=210,
                    value="\n".join(u_cfg.get("email_recipients") or []),
                    key=f"s_em_{uid}",
                    placeholder="name@tta.or.kr"
                )
                _subj_in = ""  # email_subject_prefix 미사용 (고정 형식으로 자동 생성)

            st.markdown('---')
            if st.button("💾 설정 저장", type="primary", key=f"s_save_{uid}"):
                from news_engine import save_unit_settings as _sus
                _ok = _sus(uid, {
                    "keywords":              [k.strip() for k in _kw_in.split("\n") if k.strip()],
                    "google_alerts_rss":     [u.strip() for u in _rss_in.split("\n") if u.strip()],
                    "email_recipients":      [e.strip() for e in _email_in.split("\n") if e.strip()],
                    "sender_name":           _sender_in.strip(),
                    "email_subject_prefix":  _subj_in.strip(),
                })
                if _ok:
                    st.success(f"✅ {unit['display_name']} 설정 저장 완료.")
                    st.rerun()
                else:
                    st.error("저장 실패. 오류 로그를 확인하세요.")

        if _is_admin and _set_tabs and _set_units:
            for _st_tab, _st_unit in zip(_set_tabs, _set_units):
                with _st_tab:
                    _do_unit_settings_panel(_st_unit)
        elif not _is_admin and _set_units:
            _do_unit_settings_panel(_set_units[0])


# ===== 시스템 설정 페이지 (관리자 전용) =====
elif selected == "⚙️ 시스템 설정":
    st.markdown('<h1 class="main-header">⚙️ 시스템 설정</h1>', unsafe_allow_html=True)
    
    cfg = load_config()
    
    # ===== 🔥 커스텀 탭 UI =====
    if 'settings_tab' not in st.session_state or st.session_state.settings_tab in ('keywords', 'email'):
        st.session_state.settings_tab = 'api'

    col_tab1, col_tab2, col_tab3, col_tab4 = st.columns(4)

    with col_tab1:
        if st.button("🔑 API 키", key="tab_api_settings", use_container_width=True):
            st.session_state.settings_tab = 'api'

    with col_tab2:
        if st.button("⏰ 스케줄", key="tab_schedule_settings", use_container_width=True):
            st.session_state.settings_tab = 'schedule'

    with col_tab3:
        if st.button("🏢 단 멤버십", key="tab_units_settings", use_container_width=True):
            st.session_state.settings_tab = 'units'

    with col_tab4:
        if st.button("📋 사용자 로그", key="tab_log_settings", use_container_width=True):
            st.session_state.settings_tab = 'logs'

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
        st.caption("각 단에 담당자 이메일을 배정합니다. 배정된 계정은 해당 단의 RSS·키워드·이메일을 ⚙️ 단별 설정에서 편집할 수 있습니다.")
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

    elif st.session_state.settings_tab == 'logs':
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        st.markdown("### 📋 사용자 활동 로그")
        st.caption("접속 및 주요 기능 사용 이력을 조회합니다.")

        # ── 로그 기능 진단 버튼 ─────────────────────────────────────────────────
        if st.button("🔧 로그 기능 동작 테스트", key="log_diag_btn"):
            try:
                log_user_activity(_user_email, 'diag_test', {'source': 'admin_panel'})
                import time as _t_diag
                _t_diag.sleep(0.3)
                _diag_logs = get_activity_logs(limit=5, days=1)
                _diag_ok = any(r['action'] == 'diag_test' for r in _diag_logs)
                if _diag_ok:
                    st.success("✅ 로그 기능 정상 — DB 쓰기·읽기 모두 확인")
                    # 테스트 레코드 즉시 삭제
                    from news_engine import DB_ENGINE
                    from sqlalchemy import text as _dt
                    with DB_ENGINE.connect() as _dc:
                        _dc.execute(_dt("DELETE FROM user_activity_logs WHERE action='diag_test'"))
                        _dc.commit()
                else:
                    st.error("❌ 로그 쓰기 실패 — DB에 기록되지 않음. 서버 로그를 확인하세요.")
            except Exception as _de:
                st.error(f"❌ 진단 중 오류: {_de}")

        st.markdown("---")

        # ── 필터 ─────────────────────────────────────────────────────────────
        _lf_col1, _lf_col2, _lf_col3 = st.columns([2, 2, 1])
        with _lf_col1:
            _lf_email = st.text_input(
                "이메일 필터",
                placeholder="전체 (비워두면 전체 조회)",
                key="log_filter_email",
            )
        with _lf_col2:
            _ACTION_LABELS = {
                "전체": None,
                "login (로그인)": "login",
                "logout (로그아웃)": "logout",
                "daily_run (일일수집)": "daily_run",
                "rag_search (AI검색)": "rag_search",
                "weekly_report (주간리포트)": "weekly_report",
                "monthly_report (월간리포트)": "monthly_report",
                "settings_save (설정저장)": "settings_save",
                "batch_analyze (배치분석)": "batch_analyze",
            }
            _lf_action_label = st.selectbox(
                "액션 필터",
                list(_ACTION_LABELS.keys()),
                key="log_filter_action",
            )
            _lf_action = _ACTION_LABELS[_lf_action_label]
        with _lf_col3:
            _lf_days = st.number_input(
                "최근 N일",
                min_value=1, max_value=365, value=30,
                key="log_filter_days",
            )

        # ── 조회 ─────────────────────────────────────────────────────────────
        _logs = get_activity_logs(
            limit=500,
            user_email=_lf_email.strip() or None,
            action=_lf_action,
            days=int(_lf_days),
        )

        if _logs:
            _sm1, _sm2, _sm3, _sm4 = st.columns(4)
            _unique_users = len({r['user_email'] for r in _logs})
            _login_cnt    = sum(1 for r in _logs if r['action'] == 'login')
            _run_cnt      = sum(1 for r in _logs if r['action'] == 'daily_run')
            _search_cnt   = sum(1 for r in _logs if r['action'] == 'rag_search')
            _sm1.metric("총 기록", f"{len(_logs):,}건")
            _sm2.metric("접속 사용자", f"{_unique_users}명")
            _sm3.metric("일일수집 실행", f"{_run_cnt}회")
            _sm4.metric("AI 검색", f"{_search_cnt}회")
            st.markdown("---")

            import pandas as _pd_log
            import json as _json_log
            _log_df = _pd_log.DataFrame(_logs)
            _log_df['created_at'] = _pd_log.to_datetime(_log_df['created_at'])
            _log_df = _log_df.rename(columns={
                'id': 'ID', 'user_email': '사용자',
                'action': '액션', 'detail': '상세',
                'created_at': '시각',
            })
            _log_df['시각'] = _log_df['시각'].dt.strftime('%Y-%m-%d %H:%M:%S')

            # detail JSON에서 session_duration 추출 → 세션 시간 컬럼
            def _extract_session(detail_str):
                if not detail_str:
                    return ''
                try:
                    d = _json_log.loads(detail_str)
                    return d.get('session_duration', '')
                except Exception:
                    return ''

            _log_df['세션 시간'] = _log_df['상세'].apply(_extract_session)

            st.dataframe(
                _log_df[['시각', '사용자', '액션', '세션 시간', '상세']],
                use_container_width=True,
                height=500,
                hide_index=True,
            )
            _csv_buf = _log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "⬇️ CSV 다운로드",
                data=_csv_buf,
                file_name=f"user_activity_log_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("조회된 로그가 없습니다.")

        st.markdown('</div>', unsafe_allow_html=True)
