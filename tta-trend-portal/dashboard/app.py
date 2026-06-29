import html
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from artifact_utils import fetch_report_artifacts
from db import fetch_articles, fetch_sources, fetch_stats, get_engine, is_postgres
from graph_utils import build_edges, graph_summary
from radar_utils import (
    COMPANY_NORMALIZE,
    COUNTRY_NORMALIZE,
    cluster_counts,
    cluster_detail,
    company_counts,
    country_counts,
    entity_detail,
    entity_tech_matrix,
    entity_trend,
    filter_home_articles,
    issue_board,
    issue_timeline,
    new_entities,
    split_recent_baseline,
    trending_keywords,
    unit_issue_summary,
)
from search import build_answer, clean_text, hybrid_search
from workflow_utils import STATUS_OPTIONS, merge_issue_actions, save_issue_actions


st.set_page_config(
    page_title="TTA ICT Trend Radar",
    page_icon="TTA",
    layout="wide",
    initial_sidebar_state="collapsed",
)


UNIT_OPTIONS = {
    "전체": None,
    "표준기획단": 1,
    "표준혁신단": 2,
    "AI융합표준단": 3,
    "전파네트워크표준단": 4,
}

UNIT_NAMES = {value: label for label, value in UNIT_OPTIONS.items() if value is not None}

UNIT_COLORS = {
    "표준기획단": "#0284c7",
    "표준혁신단": "#059669",
    "AI융합표준단": "#7c3aed",
    "전파네트워크표준단": "#b45309",
}


def is_embed_mode() -> bool:
    value = st.query_params.get("embed", "")
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).lower() in {"1", "true", "yes", "portal"}


def apply_portal_style(embed_mode: bool):
    top_padding = "0.7rem" if embed_mode else "1.5rem"
    st.markdown(
        f"""
        <style>
        html, body, [data-testid="stAppViewContainer"] {{
            background: #f6f8fb;
            color: #0f172a;
        }}
        .block-container {{
            padding-top: {top_padding};
            padding-bottom: 2rem;
            max-width: 1320px;
        }}
        div[data-testid="stTabs"] button {{ font-weight: 800; }}
        .stDataFrame, div[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}
        div[data-testid="stAlert"] {{ border-radius: 12px; }}

        /* ── Hero ──────────────────────────────── */
        .portal-hero {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            border: 1px solid #1e3a5f;
            border-radius: 18px;
            padding: 30px 32px 26px 32px;
            background: linear-gradient(135deg, #071427 0%, #0e2b52 52%, #155e75 100%);
            color: #ffffff;
            margin-bottom: 14px;
        }}
        .portal-badge {{
            display: inline-block;
            padding: 5px 11px;
            border: 1px solid rgba(255,255,255,.26);
            border-radius: 999px;
            color: #b9e6ff;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: .09em;
            text-transform: uppercase;
            margin-bottom: 14px;
        }}
        .portal-hero h1 {{
            margin: 0 0 10px 0;
            font-size: 1.95rem;
            line-height: 1.12;
            font-weight: 900;
            letter-spacing: -.01em;
        }}
        .hero-desc {{
            margin: 0 0 22px 0;
            color: #d7e6f5;
            font-size: 0.93rem;
            line-height: 1.7;
            max-width: 780px;
        }}
        .hero-stat-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
        }}
        .hero-stat-card {{
            background: rgba(255,255,255,.1);
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 13px;
            padding: 13px 15px;
        }}
        .hero-stat-label {{
            font-size: 11px;
            color: #b9e6ff;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
        }}
        .hero-stat-value {{
            font-size: 22px;
            font-weight: 900;
            margin-top: 4px;
            line-height: 1;
        }}
        .hero-stat-sub {{
            font-size: 11px;
            color: #c9d8e8;
            margin-top: 5px;
        }}

        /* ── Action cards ───────────────────────── */
        .action-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
            margin-bottom: 12px;
        }}
        .action-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            padding: 17px 19px;
            box-shadow: 0 10px 24px rgba(15,23,42,.05);
        }}
        .action-tag {{
            font-size: 11px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: .07em;
            margin-bottom: 7px;
        }}
        .action-title {{
            font-size: 18px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 7px;
            line-height: 1.2;
        }}
        .action-desc {{
            font-size: 13px;
            line-height: 1.55;
            color: #475569;
        }}

        /* ── Bottom panels ──────────────────────── */
        .bottom-panels {{
            display: grid;
            grid-template-columns: 1.3fr .7fr;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .workflow-panel {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            padding: 16px 18px;
        }}
        .panel-title {{
            font-size: 14px;
            font-weight: 900;
            color: #0f172a;
            margin-bottom: 12px;
        }}
        .workflow-steps {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
        .workflow-step {{
            border-left: 4px solid #94a3b8;
            border-radius: 0;
            padding-left: 10px;
            color: #475569;
            font-size: 12.5px;
            line-height: 1.5;
        }}
        .query-panel {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #0f172a;
            color: #ffffff;
            border-radius: 14px;
            padding: 16px 18px;
        }}
        .query-panel-title {{
            font-size: 12px;
            color: #93c5fd;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .06em;
            margin-bottom: 10px;
        }}
        .query-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
        }}
        .query-chip {{
            padding: 6px 10px;
            border-radius: 999px;
            background: #1e293b;
            color: #dbeafe;
            font-size: 12px;
        }}

        /* ── Quick query panel (QA tab) ─────────── */
        .quick-query-panel {{
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            background: #ffffff;
            padding: 14px 14px 4px 14px;
            margin-bottom: 10px;
        }}

        /* ── Intelligence home ─────────────────── */
        .home-section-title {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            font-size: 1.05rem;
            font-weight: 950;
            color: #0f172a;
            margin: 12px 0 8px 0;
        }}
        .home-section-sub {{
            font-size: 0.82rem;
            color: #64748b;
            margin: -4px 0 10px 0;
        }}
        .signal-grid {{
            display: grid;
            grid-template-columns: 1.25fr .75fr;
            gap: 13px;
            margin-bottom: 14px;
        }}
        .briefing-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            padding: 17px 18px;
            box-shadow: 0 10px 24px rgba(15,23,42,.05);
        }}
        .briefing-card.dark {{
            background: linear-gradient(135deg, #0f172a 0%, #164e63 100%);
            color: #ffffff;
            border-color: #164e63;
        }}
        .briefing-eyebrow {{
            color: #0284c7;
            font-size: 11px;
            font-weight: 950;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }}
        .briefing-card.dark .briefing-eyebrow {{ color: #a5f3fc; }}
        .briefing-title {{
            font-size: 1.12rem;
            font-weight: 950;
            color: #0f172a;
            line-height: 1.35;
            margin-bottom: 8px;
        }}
        .briefing-card.dark .briefing-title {{ color: #ffffff; }}
        .briefing-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
            margin: 9px 0;
        }}
        .meta-pill {{
            border-radius: 999px;
            padding: 5px 9px;
            background: #eff6ff;
            color: #075985;
            font-size: 11px;
            font-weight: 800;
        }}
        .briefing-card.dark .meta-pill {{
            background: rgba(255,255,255,.13);
            color: #e0f2fe;
        }}
        .briefing-body {{
            color: #475569;
            font-size: 0.84rem;
            line-height: 1.58;
        }}
        .briefing-card.dark .briefing-body {{ color: #dbeafe; }}
        .briefing-link {{
            display: inline-block;
            margin-top: 9px;
            color: #0369a1;
            font-size: 0.8rem;
            font-weight: 900;
            text-decoration: none;
        }}
        .briefing-card.dark .briefing-link {{ color: #bae6fd; }}
        .mini-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }}
        .mini-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 13px;
            padding: 13px 14px;
            min-height: 112px;
        }}
        .mini-label {{
            color: #64748b;
            font-size: 11px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: .06em;
            margin-bottom: 5px;
        }}
        .mini-value {{
            color: #0f172a;
            font-size: 1.25rem;
            font-weight: 950;
            line-height: 1.15;
        }}
        .mini-desc {{
            color: #64748b;
            font-size: 0.78rem;
            line-height: 1.45;
            margin-top: 8px;
        }}
        .chip-cloud {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 14px;
        }}
        .radar-chip {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
            border: 1px solid #cbd5e1;
            border-radius: 999px;
            background: #ffffff;
            padding: 7px 10px;
            color: #0f172a;
            font-size: 0.8rem;
            font-weight: 850;
        }}
        .radar-chip span {{
            color: #0369a1;
            font-size: 0.72rem;
            font-weight: 950;
        }}
        .home-two-col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 14px;
        }}
        .list-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            padding: 15px 16px;
        }}
        .list-row {{
            border-top: 1px solid #e2e8f0;
            padding: 10px 0;
        }}
        .list-row:first-of-type {{ border-top: 0; padding-top: 2px; }}
        .row-title {{
            color: #0f172a;
            font-size: 0.86rem;
            font-weight: 900;
            line-height: 1.35;
        }}
        .row-meta {{
            color: #64748b;
            font-size: 0.74rem;
            margin-top: 4px;
        }}
        .unit-brief-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }}
        .unit-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 13px;
            padding: 13px 14px;
        }}
        .unit-name {{
            font-weight: 950;
            color: #0f172a;
            margin-bottom: 6px;
        }}
        .unit-issue {{
            color: #475569;
            font-size: 0.8rem;
            line-height: 1.45;
        }}
        @media (max-width: 900px) {{
            .hero-stat-grid,
            .workflow-steps,
            .signal-grid,
            .home-two-col {{
                grid-template-columns: 1fr;
            }}
            .portal-hero {{
                padding: 22px 20px;
            }}
        }}

        /* ── Executive KPI strip ──────────────────── */
        .kpi-strip {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 14px;
        }}
        .kpi-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            padding: 14px 16px;
        }}
        .kpi-label {{
            font-size: 10px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: .07em;
            color: #64748b;
            margin-bottom: 5px;
        }}
        .kpi-value {{
            font-size: 22px;
            font-weight: 900;
            color: #0f172a;
            line-height: 1;
        }}
        .kpi-value.red {{ color: #b91c1c; }}
        .kpi-value.small {{ font-size: 14px; margin-top: 4px; }}
        .kpi-sub {{ font-size: 11px; color: #64748b; margin-top: 4px; }}

        /* ── Keyword bar chart ────────────────────── */
        .kw-bar-card {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 14px;
            padding: 17px 18px;
            height: 100%;
        }}
        .kw-eyebrow {{
            font-size: 11px;
            font-weight: 900;
            color: #0284c7;
            text-transform: uppercase;
            letter-spacing: .08em;
            margin-bottom: 12px;
        }}
        .kw-bar-row {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 9px;
        }}
        .kw-bar-label {{ font-size: 12px; color: #0f172a; font-weight: 850; min-width: 80px; }}
        .kw-bar-bg {{ flex: 1; height: 5px; background: #e2e8f0; border-radius: 3px; }}
        .kw-bar-fill {{ height: 5px; border-radius: 3px; background: #0284c7; }}
        .kw-bar-pct {{ font-size: 11px; font-weight: 900; color: #0369a1; min-width: 36px; text-align: right; }}

        /* ── Urgent section ───────────────────────── */
        .urgent-banner {{
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-left: 3px solid #e24b4a;
            border-radius: 0 14px 14px 0;
            padding: 14px 16px;
            margin-bottom: 14px;
        }}
        .urgent-title {{
            font-size: 10px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: .07em;
            color: #b91c1c;
            margin-bottom: 10px;
        }}
        .urgent-item {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 7px 0;
            border-bottom: 1px solid #f1f5f9;
        }}
        .urgent-item:last-child {{ border-bottom: 0; }}
        .urgent-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }}
        .urgent-text {{ font-size: 12.5px; color: #0f172a; line-height: 1.4; }}
        .urgent-meta {{ font-size: 11px; color: #64748b; margin-top: 2px; }}

        /* ── Unit card header ─────────────────────── */
        .unit-card-header {{ display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }}
        .unit-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}

        @media (max-width: 900px) {{
            .kpi-strip {{ grid-template-columns: 1fr 1fr; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def check_staff_access(embed_mode: bool = False) -> bool:
    allowed_domain = os.getenv("TTA_ALLOWED_EMAIL_DOMAIN", "tta.or.kr").lower()
    container = st.container() if embed_mode else st.sidebar
    with container:
        st.header("접근 확인")
        email = st.text_input("TTA 이메일", value=st.session_state.get("staff_email", ""))
        if email:
            st.session_state["staff_email"] = email.strip()
        if not email:
            st.info("TTA 이메일을 입력하세요.")
            return False
        domain_ok = email.lower().endswith(f"@{allowed_domain}")
        if not domain_ok:
            st.error(f"허용 도메인: @{allowed_domain}")
            return False
        st.success("직원 도메인 확인")
    return True


@st.cache_resource(show_spinner=False)
def cached_engine():
    return get_engine()


def article_table(df: pd.DataFrame):
    if df.empty:
        st.info("검색 결과가 없습니다.")
        return
    show = df.copy()
    for col in ["published", "collected_at"]:
        if col in show.columns:
            show[col] = show[col].astype(str).str.slice(0, 19)
    cols = [c for c in ["title", "source", "published", "quality_score", "similarity", "search_type", "link"] if c in show.columns]
    st.dataframe(show[cols], use_container_width=True, hide_index=True)


def render_header(stats: dict, embed_mode: bool):
    articles = stats.get("articles", 0)
    analyzed = stats.get("analyzed", 0)
    embeddings = stats.get("embeddings", 0)
    missing = max(analyzed - embeddings, 0)
    today = datetime.now().strftime("%Y.%m.%d")

    st.markdown(
        f"""
        <div class="portal-hero">
          <div class="portal-badge">TTA Intelligence Radar</div>
          <h1>오늘의 ICT 표준화 신호를<br>한 화면에서 읽습니다</h1>
          <p class="hero-desc">뉴스 원장, AI 분석 결과, 표준화 대응 후보, 관계 맵, 주간 보고서를 연결해 TTA 직원이 바로 판단할 수 있는 내부 인텔리전스 포털입니다.</p>
          <div class="hero-stat-grid">
            <div class="hero-stat-card">
              <div class="hero-stat-label">전체 기사</div>
              <div class="hero-stat-value">{articles:,}</div>
              <div class="hero-stat-sub">수집·저장된 뉴스 원장</div>
            </div>
            <div class="hero-stat-card">
              <div class="hero-stat-label">AI 분석</div>
              <div class="hero-stat-value">{analyzed:,}</div>
              <div class="hero-stat-sub">GPT 분석 완료 기사</div>
            </div>
            <div class="hero-stat-card">
              <div class="hero-stat-label">RAG 임베딩</div>
              <div class="hero-stat-value">{embeddings:,}</div>
              <div class="hero-stat-sub">의미 검색 가능 기사</div>
            </div>
            <div class="hero-stat-card">
              <div class="hero-stat-label">업데이트</div>
              <div class="hero-stat-value">Daily</div>
              <div class="hero-stat-sub">{today} 기준</div>
            </div>
          </div>
        </div>

        <div class="action-grid">
          <div class="action-card">
            <div class="action-tag" style="color:#0369a1;">Daily Radar</div>
            <div class="action-title">오늘의 레이더</div>
            <div class="action-desc">급등 키워드, 신규 엔티티, 단별 추천 이슈를 바로 확인합니다.</div>
          </div>
          <div class="action-card">
            <div class="action-tag" style="color:#7c2d12;">Action Board</div>
            <div class="action-title">표준화 대응 보드</div>
            <div class="action-desc">영향도와 긴급도를 보고 검토 상태와 조치 메모를 남깁니다.</div>
          </div>
          <div class="action-card">
            <div class="action-tag" style="color:#047857;">Reports</div>
            <div class="action-title">보고서 보관함</div>
            <div class="action-desc">Google Docs와 Excel 산출물을 한 곳에서 조회합니다.</div>
          </div>
          <div class="action-card">
            <div class="action-tag" style="color:#6d28d9;">Issue Map</div>
            <div class="action-title">이슈 맵</div>
            <div class="action-desc">기업·기술·국가 공출현 관계를 그래프로 시각화합니다.</div>
          </div>
        </div>

        <div class="bottom-panels">
          <div class="workflow-panel">
            <div class="panel-title">직원이 바로 쓰는 판단 흐름</div>
            <div class="workflow-steps">
              <div class="workflow-step" style="border-left-color:#0284c7;"><strong style="color:#0f172a;">1. 감지</strong><br>오늘 급등한 기술과 엔티티 확인</div>
              <div class="workflow-step" style="border-left-color:#b45309;"><strong style="color:#0f172a;">2. 선별</strong><br>영향도·긴급도 기준 후보 분류</div>
              <div class="workflow-step" style="border-left-color:#047857;"><strong style="color:#0f172a;">3. 근거</strong><br>RAG 검색으로 관련 기사 확인</div>
              <div class="workflow-step" style="border-left-color:#6d28d9;"><strong style="color:#0f172a;">4. 공유</strong><br>보고서와 조치 메모로 확산</div>
            </div>
          </div>
          <div class="query-panel">
            <div class="query-panel-title">추천 검색어</div>
            <div class="query-chips">
              <span class="query-chip">AI-RAN 표준화</span>
              <span class="query-chip">NTN 위성통신</span>
              <span class="query-chip">6G 국제표준</span>
              <span class="query-chip">양자통신</span>
              <span class="query-chip">오픈랜 정책</span>
              <span class="query-chip">B5G 주파수</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not embed_mode:
        st.caption("별도 대시보드 프로그램입니다. 기존 운영 코드는 수정하거나 import하지 않습니다.")


@st.cache_data(
    ttl=60 * 60 * 8,
    show_spinner="탑 시그널 RAG 요약 생성 중…",
)
def build_rag_top_signal(_engine, issue_title: str, _date_key: str) -> str:
    """Return a 3-sentence GPT-4o brief for the top issue, cached per day."""
    if not issue_title:
        return ""
    try:
        results, _ = hybrid_search(
            _engine,
            issue_title,
            days=90,
            unit_id=None,
            top_k=8,
            analyzed_only=True,
        )
        if results.empty:
            return ""
        prompt = (
            f"다음 ICT 표준화 이슈를 TTA 직원이 바로 활용할 수 있도록 3문장으로 요약해 주세요. "
            f"첫 문장: 현황과 핵심 사실. 두 번째 문장: 표준화 관련 영향. 세 번째 문장: 권장 조치.\n"
            f"이슈: {issue_title}"
        )
        return build_answer(prompt, results)
    except Exception:
        return ""


def render_quick_queries():
    st.markdown('<div class="quick-query-panel"><strong>빠른 질문</strong>', unsafe_allow_html=True)
    examples = [
        "최근 3개월 AI-RAN 표준화 이슈",
        "NTN 위성통신 정책 변화 시사점",
        "6G 국제표준 경쟁 동향",
        "양자통신 관련 기업과 국가",
    ]
    cols = st.columns(4)
    for idx, example in enumerate(examples):
        if cols[idx].button(example, key=f"quick_query_{idx}", use_container_width=True):
            st.session_state["portal_query"] = example
    st.markdown("</div>", unsafe_allow_html=True)


def esc(value, max_len: int | None = None) -> str:
    if pd.isna(value):
        value = ""
    text = clean_text(value, max_len or 1200)
    if max_len and len(text) >= max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return html.escape(text)


def first_present(*values) -> str:
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def date_label(value) -> str:
    if value is None or pd.isna(value):
        return ""
    try:
        return str(pd.to_datetime(value, errors="coerce"))[:10]
    except Exception:
        return str(value)[:10]


def choose_home_window(df: pd.DataFrame) -> tuple[int, pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return 30, df, df
    for days in [7, 14, 30, 90]:
        recent, baseline = split_recent_baseline(df, days)
        if len(recent) >= 3:
            return days, recent, baseline
    recent, baseline = split_recent_baseline(df, 365)
    if recent.empty:
        recent = df.head(50).copy()
    return 365, recent, baseline


def select_daily_pool(df: pd.DataFrame, min_articles: int = 8) -> pd.DataFrame:
    """오늘(가장 최근 수집일) 분석 기사 풀을 우선 반환.
    9시 파이프라인이 그날치를 분석해 넣으면 Executive Brief가 그 풀에서 갱신된다.
    그날치가 min_articles 미만이면 전체(df)를 그대로 반환해 폴백한다."""
    if df.empty or "collected_at" not in df.columns:
        return df
    dated = df.copy()
    dated["_collected_d"] = pd.to_datetime(dated["collected_at"], errors="coerce")
    if not dated["_collected_d"].notna().any():
        return df
    latest_day = dated["_collected_d"].max().normalize()
    today_pool = dated[dated["_collected_d"] >= latest_day]
    if len(today_pool) >= min_articles:
        return today_pool.drop(columns=["_collected_d"])
    return df


def daily_pool_label(df: pd.DataFrame) -> str:
    """Brief가 어느 날짜 기사에서 나왔는지 라벨 (부제 표기용).
    단일 수집일이면 그 날짜, 여러 날이 섞였으면(폴백) '최근'으로 정직하게 표기."""
    if df.empty or "collected_at" not in df.columns:
        return "최근"
    d = pd.to_datetime(df["collected_at"], errors="coerce").dropna()
    if d.empty:
        return "최근"
    days = d.dt.normalize().unique()
    if len(days) == 1:
        return f"{d.max():%Y-%m-%d}"
    return "최근"


def render_chip_cloud(chips: pd.DataFrame, label_col: str, score_col: str, fallback: str):
    if chips.empty:
        st.info(fallback)
        return
    html_parts = ['<div class="chip-cloud">']
    for _, row in chips.head(12).iterrows():
        label = esc(row.get(label_col), 38)
        category = esc(row.get("구분", ""), 12)
        score = esc(row.get(score_col, ""), 16)
        html_parts.append(f'<div class="radar-chip">{label}<span>{category} {score}</span></div>')
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


IMPACT_BADGE = {
    "Critical": ("🔴", "#f87171", "rgba(248,113,113,.18)"),
    "High": ("🟠", "#fb923c", "rgba(251,146,60,.18)"),
    "Medium": ("🟡", "#fbbf24", "rgba(251,191,36,.16)"),
    "Low": ("🟢", "#34d399", "rgba(52,211,153,.16)"),
}


def impact_badge_html(level: str) -> str:
    icon, color, bg = IMPACT_BADGE.get(str(level), ("", "", ""))
    if not icon:
        return ""
    return f'<span class="meta-pill" style="background:{bg};color:{color};">{icon} {esc(level)}</span>'


def _entity_ribbon_html(row: pd.Series) -> str:
    """국가·기업·기술·표준 회의체를 한눈에 보이는 4분류 칩 리본.
    표준 회의체가 비면 'TTA 기여 기회'로 신호화 (포지션 매트릭스 철학과 일치)."""
    mapping = [("🌐", "국가"), ("🏢", "기업"), ("⚙️", "기술"), ("📐", "표준회의체")]
    lines = []
    for icon, col in mapping:
        val = str(row.get(col, "") or "").strip()
        if val:
            lines.append(f"<span style='color:#64748b;'>{icon}</span> {esc(val, 46)}")
        elif col == "표준회의체":
            lines.append(f"<span style='color:#64748b;'>{icon}</span> <span style='color:#94a3b8;font-style:italic;'>표준 연계 미식별 · 기여 기회</span>")
    return "<div style='font-size:0.78rem;line-height:1.55;margin-top:6px;'>" + "<br>".join(lines) + "</div>"


def _render_brief_card(row: pd.Series, idx: int):
    """Executive Brief 카드 1장 — 영향등급·긴급도·종합점수·왜중요·TTA대응·엔티티리본."""
    level = str(row.get("영향등급", "") or "")
    why = str(row.get("왜 중요한가", "") or "")
    tta = str(row.get("TTA 대응과제", "") or "")
    score = row.get("종합점수")
    score_pill = f"  <span class='meta-pill'>종합 {esc(score)}</span>" if pd.notna(score) else ""
    st.markdown(
        impact_badge_html(level)
        + f"  <span class='meta-pill'>긴급도 {esc(row.get('긴급도'))}/10</span>"
        + f"  <span class='meta-pill'>표준화 {esc(row.get('표준화 연계성'))}/10</span>"
        + score_pill,
        unsafe_allow_html=True,
    )
    st.markdown(f"**{esc(row.get('이슈 후보'), 90)}**")
    if why:
        st.caption("왜 중요한가: " + esc(why, 150))
    st.markdown(_entity_ribbon_html(row), unsafe_allow_html=True)
    if tta:
        st.markdown(
            f"<div style='font-size:0.82rem;color:#0369a1;margin-top:6px;'>TTA 대응: {esc(tta, 120)}</div>",
            unsafe_allow_html=True,
        )
    bc1, bc2 = st.columns(2)
    bc1.link_button("자세히 보기", str(row.get("관련 기사", "") or "#"), use_container_width=True)
    if bc2.button("분석실로", key=f"exec_brief_qa_{idx}", use_container_width=True):
        st.session_state["portal_query"] = str(row.get("이슈 후보", ""))
        st.toast("질문형 분석실 입력창에 준비했습니다. QA 탭으로 이동하세요.")


def render_executive_brief_top(board: pd.DataFrame, count: int = 6):
    """오늘 반드시 봐야 할 핵심 이슈 — 홈 최상단 카드 (2×3, 6장).
    매일 분석된 뉴스에서 5축 점수 + 다양성(MMR)으로 선정된 board를 받는다."""
    if board.empty:
        st.info("오늘의 핵심 이슈를 만들 분석 기사가 아직 부족합니다.")
        return
    top = board.head(count)
    records = list(top.iterrows())
    for chunk_start in range(0, len(records), 3):
        cols = st.columns(3)
        for offset, (_, row) in enumerate(records[chunk_start:chunk_start + 3]):
            idx = chunk_start + offset
            with cols[offset]:
                with st.container(border=True):
                    _render_brief_card(row, idx)


def render_issue_cards(board: pd.DataFrame, rag_summary: str = ""):
    if board.empty:
        st.info("표준화 대응 후보를 만들 수 있는 분석 기사가 아직 부족합니다.")
        return

    top = board.iloc[0]
    body = esc(rag_summary, 400) if rag_summary else esc(top.get("권장 조치"), 260)
    rag_badge = (
        '<span class="meta-pill" style="background:rgba(34,211,238,.18);color:#a5f3fc;">RAG 요약</span>'
        if rag_summary
        else ""
    )
    top_level = str(top.get("영향등급", "") or "")
    # 선정 근거 — 직원이 "왜 이게 1순위인가"를 알 수 있도록 명시
    rationale_bits = []
    if top_level:
        rationale_bits.append(f"AI 영향등급 {top_level}")
    rationale_bits.append(f"영향도 {esc(top.get('영향도'))}·긴급도 {esc(top.get('긴급도'))} 종합 1순위")
    rationale = " · ".join(rationale_bits)
    # TTA 대응과제 블록
    tta_action = str(top.get("TTA 대응과제", "") or "").strip()
    action_html = (
        f'<div class="briefing-body" style="margin-top:8px;border-top:1px solid rgba(255,255,255,.12);padding-top:8px;">'
        f'<strong style="color:#a5f3fc;">TTA 대응과제</strong><br>{esc(tta_action, 300)}</div>'
        if tta_action
        else ""
    )
    st.markdown(
        f"""
        <div class="briefing-card dark" style="margin-bottom:12px;">
          <div class="briefing-eyebrow">Top Signal · {esc(rationale)}</div>
          <div class="briefing-title">{esc(top.get("이슈 후보"), 180)}</div>
          <div class="briefing-meta">
            {impact_badge_html(top_level)}
            <span class="meta-pill">영향도 {esc(top.get("영향도"))}/10</span>
            <span class="meta-pill">긴급도 {esc(top.get("긴급도"))}/10</span>
            <span class="meta-pill">{esc(top.get("담당 단"))}</span>
            {rag_badge}
          </div>
          <div class="briefing-body">{body}</div>
          {action_html}
          <a class="briefing-link" href="{esc(top.get("관련 기사"))}" target="_blank">근거 기사 열기</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("이 이슈를 분석실에서 더 보기", key="top_signal_to_qa", use_container_width=True):
        st.session_state["portal_query"] = str(top.get("이슈 후보", ""))
        st.toast("질문형 분석실 입력창에 준비했습니다. QA 탭으로 이동하세요.")

    html_parts = ['<div class="mini-grid">']
    for _, row in board.head(4).iterrows():
        unit_raw = str(row.get("담당 단", ""))
        dot_color = UNIT_COLORS.get(unit_raw, "#64748b")
        level = str(row.get("영향등급", "") or "")
        icon = IMPACT_BADGE.get(level, ("", "", ""))[0]
        level_tag = f"{icon} {esc(level)} · " if icon else ""
        html_parts.append(f"""
        <div class="mini-card">
          <div class="unit-card-header" style="margin-bottom:4px;">
            <div class="unit-dot" style="background:{dot_color};"></div>
            <div class="mini-label">{esc(unit_raw)}</div>
          </div>
          <div class="mini-value">{esc(row.get("이슈 후보"), 58)}</div>
          <div class="mini-desc">{level_tag}영향도 {esc(row.get("영향도"))}/10 · 긴급도 {esc(row.get("긴급도"))}/10<br>{esc(row.get("출처"), 35)}</div>
        </div>""")
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_unit_briefs(unit_summary: pd.DataFrame):
    if unit_summary.empty:
        st.info("단별 추천 이슈가 아직 없습니다.")
        return
    html_parts = ['<div class="unit-brief-grid">']
    for _, row in unit_summary.head(8).iterrows():
        unit_raw = first_present(row.get("단"), "")
        dot_color = UNIT_COLORS.get(unit_raw, "#64748b")
        html_parts.append(f"""
        <div class="unit-card">
          <div class="unit-card-header">
            <div class="unit-dot" style="background:{dot_color};"></div>
            <div class="unit-name">{esc(unit_raw, 40)}</div>
          </div>
          <div class="unit-issue">{esc(row.get("추천 이슈"), 115)}</div>
          <div class="row-meta">영향도 {esc(row.get("영향도"))}/10 · 긴급도 {esc(row.get("긴급도"))}/10</div>
        </div>""")
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_kpi_strip(stats: dict, board: pd.DataFrame, keywords: pd.DataFrame, reports: pd.DataFrame):
    total = stats.get("articles", 0)
    urgent_count = 0
    if not board.empty and "긴급도" in board.columns:
        urgent_count = int((pd.to_numeric(board["긴급도"], errors="coerce") >= 8).sum())
    kw_count = len(keywords)
    latest_report = ""
    if not reports.empty and "title" in reports.columns:
        latest_report = esc(str(reports.iloc[0].get("title", "")), 26)
    red_cls = " red" if urgent_count > 0 else ""
    st.markdown(
        f"""
        <div class="kpi-strip">
          <div class="kpi-card">
            <div class="kpi-label">전체 수집 기사</div>
            <div class="kpi-value">{total:,}</div>
            <div class="kpi-sub">누적 원장</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">긴급 대응 필요</div>
            <div class="kpi-value{red_cls}">{urgent_count}</div>
            <div class="kpi-sub">긴급도 8점 이상</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">급등 키워드</div>
            <div class="kpi-value">{kw_count}</div>
            <div class="kpi-sub">이번 기간 감지</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">최신 보고서</div>
            <div class="kpi-value small">{latest_report if latest_report else "—"}</div>
            <div class="kpi-sub">보고서 보관함</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_keyword_bars(keywords: pd.DataFrame):
    if keywords.empty:
        st.info("급등 키워드 신호가 없습니다.")
        return
    rows = keywords.head(7)
    scores = pd.to_numeric(rows.get("레이더점수", pd.Series(dtype=float)), errors="coerce").fillna(0)
    max_score = float(scores.max()) or 1.0
    html_parts = ['<div class="kw-bar-card"><div class="kw-eyebrow">급등 키워드 TOP 7</div>']
    for _, row in rows.iterrows():
        label = esc(row.get("키워드"), 20)
        score = pd.to_numeric(row.get("레이더점수", 0), errors="coerce") or 0
        pct = round(float(score) / max_score * 100)
        category = str(row.get("구분", ""))
        pct_label = f"+{pct}%" if category == "급등" else ("신규" if category == "신규" else f"{pct}%")
        html_parts.append(f"""
        <div class="kw-bar-row">
          <div class="kw-bar-label">{label}</div>
          <div class="kw-bar-bg"><div class="kw-bar-fill" style="width:{pct}%;"></div></div>
          <div class="kw-bar-pct">{pct_label}</div>
        </div>""")
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_urgent_section(board: pd.DataFrame):
    if board.empty or "긴급도" not in board.columns:
        return
    urgent = board[pd.to_numeric(board["긴급도"], errors="coerce") >= 8].head(3)
    if urgent.empty:
        return
    items = []
    for _, row in urgent.iterrows():
        unit_raw = str(row.get("담당 단", ""))
        dot_color = UNIT_COLORS.get(unit_raw, "#64748b")
        issue = esc(row.get("이슈 후보"), 80)
        urgency = esc(row.get("긴급도"))
        items.append(f"""
        <div class="urgent-item">
          <div class="urgent-dot" style="background:{dot_color};"></div>
          <div>
            <div class="urgent-text">{issue}</div>
            <div class="urgent-meta">{esc(unit_raw)} · 긴급도 {urgency}/10</div>
          </div>
        </div>""")
    st.markdown(
        f'<div class="urgent-banner"><div class="urgent-title">즉시 검토 필요</div>{"".join(items)}</div>',
        unsafe_allow_html=True,
    )


def render_latest_lists(recent_df: pd.DataFrame, reports: pd.DataFrame):
    st.markdown('<div class="home-two-col">', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="list-card"><div class="home-section-title">최신 분석 기사</div>', unsafe_allow_html=True)
        if recent_df.empty:
            st.info("최신 분석 기사가 없습니다.")
        else:
            for _, row in recent_df.head(5).iterrows():
                st.markdown(
                    f"""
                    <div class="list-row">
                      <div class="row-title"><a href="{esc(row.get("link"))}" target="_blank">{esc(row.get("title"), 95)}</a></div>
                      <div class="row-meta">{esc(row.get("source"), 45)} · {esc(date_label(first_present(row.get("published"), row.get("collected_at"))))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="list-card"><div class="home-section-title">최근 보고서/Excel</div>', unsafe_allow_html=True)
        if reports.empty:
            st.info("등록된 보고서 산출물이 없습니다.")
        else:
            for _, row in reports.head(5).iterrows():
                url = first_present(row.get("google_doc_url"), row.get("excel_file_url"))
                count = row.get("source_article_count", 0)
                st.markdown(
                    f"""
                    <div class="list-row">
                      <div class="row-title"><a href="{esc(url)}" target="_blank">{esc(row.get("title"), 95)}</a></div>
                      <div class="row-meta">{esc(row.get("report_type"), 30)} · 기사 {esc(count)}건 · {esc(row.get("period_end"), 20)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_report_cards(view: pd.DataFrame):
    """보고서 산출물을 클릭 가능한 링크 카드로 표시. 링크 복사는 st.code의 기본 복사 버튼 활용."""
    for idx, row in view.reset_index(drop=True).iterrows():
        title = clean_text(row.get("title"), 120) or "(제목 없음)"
        rtype = clean_text(row.get("report_type"), 30)
        status = clean_text(row.get("status"), 20)
        count = row.get("source_article_count", 0)
        period = clean_text(first_present(row.get("period_end"), row.get("generated_at")), 20)
        doc_url = str(first_present(row.get("google_doc_url"), "")).strip()
        xls_url = str(first_present(row.get("excel_file_url"), "")).strip()

        with st.container(border=True):
            st.markdown(f"**{esc(title)}**")
            meta = " · ".join(p for p in [rtype, f"상태 {status}" if status else "", f"기사 {count}건", period] if p)
            st.caption(meta)
            bcols = st.columns([1, 1, 3])
            if doc_url:
                bcols[0].link_button("Google Docs 열기", doc_url, use_container_width=True)
            if xls_url:
                bcols[1].link_button("Excel 다운로드", xls_url, use_container_width=True)
            share_url = doc_url or xls_url
            if share_url:
                with bcols[2].popover("링크 복사", use_container_width=True):
                    st.caption("아래 코드블록 우측 복사 아이콘을 누르세요.")
                    st.code(share_url, language=None)
            else:
                bcols[0].caption("등록된 링크 없음")


@st.cache_data(ttl=7200, show_spinner=False)
def cached_country_counts(_engine, days: int, unit_id):
    """국가 집계 — cache 래퍼. 순수 로직은 radar_utils.country_counts."""
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return country_counts(df)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_company_counts(_engine, days: int, unit_id, top_n: int):
    """기업 집계 — cache 래퍼. 순수 로직은 radar_utils.company_counts."""
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return company_counts(df, top_n=top_n)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_issue_timeline(_engine, days: int, unit_id, top_n: int):
    """이슈 타임라인 — cache 래퍼. 순수 로직은 radar_utils.issue_timeline."""
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return issue_timeline(df, top_n=top_n)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_cluster_counts(_engine, days: int, unit_id):
    """클러스터 분포 — cache 래퍼. 순수 로직은 radar_utils.cluster_counts."""
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return cluster_counts(df)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_cluster_detail(_engine, days: int, unit_id, top_n: int):
    """클러스터 상세 카드 — cache 래퍼. 순수 로직은 radar_utils.cluster_detail."""
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return cluster_detail(df, top_n_clusters=top_n)


def render_clusters(engine, days: int, unit_id):
    """근거 기사 클러스터 — 토픽 맵(treemap) + 클러스터별 rich 카드."""
    cl = cached_cluster_counts(engine, days, unit_id)
    if cl.empty:
        st.info(
            f"클러스터 데이터 없음 — 최근 {days}일 기사에 cluster_label이 없습니다. "
            "배치(scripts/cluster_articles.py)가 아직 실행되지 않았을 수 있습니다."
        )
        return
    st.caption(f"최근 {days}일 · 임베딩 기반 K-means 군집 {len(cl)}개 · 토픽 맵")
    fig = px.treemap(cl, path=["cluster"], values="count")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # 클러스터별 근거 묶음 카드
    details = cached_cluster_detail(engine, days, unit_id, 8)
    for d in details:
        with st.expander(f"📁 {d['label']}  ·  {d['count']}건", expanded=False):
            meta = st.columns(2)
            with meta[0]:
                if d["technologies"]:
                    st.caption("핵심 키워드: " + ", ".join(d["technologies"]))
                if d["companies"]:
                    st.caption("주요 기업: " + ", ".join(d["companies"]))
                if d["countries"]:
                    st.caption("주요 국가: " + ", ".join(d["countries"]))
            with meta[1]:
                if d["sources"]:
                    st.caption("주요 출처: " + ", ".join(d["sources"]))
                if d["standards"]:
                    st.caption("표준화 포인트: " + " / ".join(d["standards"]))
            st.markdown("**대표 기사**")
            for a in d["articles"]:
                st.markdown(f"- [{esc(a['title'], 90)}]({a['link']}) · {esc(a['source'], 30)}")


STAGE_EMOJI = {"급등": "🔺", "소강": "🔻", "지속": "▪️"}


def render_issue_timeline(engine, days: int, unit_id):
    """기술 키워드 주차별 타임라인 + 급등/소강 단계."""
    tl = cached_issue_timeline(engine, days, unit_id, 8)
    if tl.empty:
        st.info(f"타임라인 데이터 없음 — 최근 {days}일 분석 기사에 key_technologies 필드가 없습니다.")
        return
    # 단계 요약 배지
    latest_stage = tl.groupby("technology")["stage"].last()
    surging = [t for t, s in latest_stage.items() if s == "급등"]
    fading = [t for t, s in latest_stage.items() if s == "소강"]
    sc1, sc2 = st.columns(2)
    sc1.caption("🔺 급등: " + (", ".join(surging) if surging else "없음"))
    sc2.caption("🔻 소강: " + (", ".join(fading) if fading else "없음"))

    fig = px.line(
        tl, x="week", y="count", color="technology", markers=True,
        labels={"week": "주차", "count": "기사 수", "technology": "기술"},
    )
    fig.update_layout(height=440, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="기술")
    st.plotly_chart(fig, use_container_width=True)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_tech_matrix(_engine, days: int, unit_id, entity_label: str, top_entities: int):
    """국가/기업 × 기술영역 매트릭스 — cache 래퍼."""
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    normalize = COUNTRY_NORMALIZE if entity_label == "국가" else COMPANY_NORMALIZE
    return entity_tech_matrix(df, entity_label, normalize, top_entities=top_entities)


def _matrix_heatmap(matrix: pd.DataFrame, title: str):
    """매트릭스 DataFrame → Plotly 히트맵 (셀에 숫자 표시)."""
    if matrix.empty:
        st.info(f"{title}: 데이터 없음")
        return
    fig = px.imshow(
        matrix.values,
        x=list(matrix.columns),
        y=list(matrix.index),
        color_continuous_scale="Blues",
        aspect="auto",
        text_auto=True,
    )
    fig.update_layout(height=40 * len(matrix) + 120, margin=dict(l=10, r=10, t=30, b=10),
                      coloraxis_showscale=False, title=title)
    fig.update_xaxes(side="top")
    st.plotly_chart(fig, use_container_width=True)


def _tta_implication(detail: dict, entity_label: str) -> str:
    """엔티티 상세에서 TTA 시사점을 데이터 기반으로 생성 (편집성 단정 배제)."""
    areas = detail.get("top_areas", [])
    if not areas:
        return "관련 기술영역 신호가 아직 약함 — 모니터링 유지."
    area_txt = " · ".join(areas[:3])
    subject = "표준화 동향" if entity_label == "국가" else "기술·표준 활동"
    return f"{area_txt} 영역에서 활발 ({detail['article_count']}건). 관련 {subject} 추적 권장."


def render_entity_drilldown(engine, days: int, unit_id, entity_label: str, options: list[str]):
    """국가/기업 선택 → 상세 카드 (집중영역·관련 엔티티·TTA 시사점·관련 기사)."""
    if not options:
        return
    key = f"drill_{entity_label}"
    picked = st.selectbox(f"{entity_label} 선택", options, key=key)
    df = fetch_articles(engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    normalize = COUNTRY_NORMALIZE if entity_label == "국가" else COMPANY_NORMALIZE
    detail = entity_detail(df, entity_label, picked, normalize)
    if detail["article_count"] == 0:
        st.info(f"{picked} 관련 기사가 최근 {days}일 내 없습니다.")
        return
    with st.container(border=True):
        st.markdown(f"#### {esc(picked)}  ·  {detail['article_count']}건")
        c1, c2 = st.columns(2)
        c1.caption("집중 기술영역: " + (", ".join(detail["top_areas"]) or "-"))
        rel = detail["top_companies"] if entity_label == "국가" else detail["top_countries"]
        rel_label = "관련 기업" if entity_label == "국가" else "관련 국가"
        c2.caption(f"{rel_label}: " + (", ".join(rel[:5]) or "-"))
        st.markdown(f"**TTA 시사점** — {esc(_tta_implication(detail, entity_label))}")
        st.markdown("**관련 기사**")
        for a in detail["articles"]:
            st.markdown(f"- [{esc(a['title'], 90)}]({a['link']}) · {esc(a['source'], 30)}")


def render_standardization_matrix(engine, days: int, unit_id):
    """국가·기업 표준화 포지션 매트릭스 (히트맵 + 드릴다운 + 급부상 TOP5)."""
    # 급부상 기업 TOP5 (최근 7일 vs 이전)
    trend_df = fetch_articles(engine, days=max(days, 30), unit_id=unit_id, analyzed_only=True, limit=3000)
    rec, base = split_recent_baseline(trend_df, 7)
    surge = entity_trend(rec, base, "기업", COMPANY_NORMALIZE, limit=5)
    if not surge.empty:
        st.markdown("**🚀 급부상 기업 TOP 5** (최근 7일 vs 이전)")
        cols = st.columns(len(surge))
        for i, (_, r) in enumerate(surge.iterrows()):
            delta = f"+{int(r['growth'])}" if r["growth"] > 0 else "0"
            cols[i].metric(str(r["name"])[:12], f"{int(r['recent'])}건", delta)

    st.markdown("##### 국가 × 기술영역")
    cm = cached_tech_matrix(engine, days, unit_id, "국가", 8)
    _matrix_heatmap(cm, "")
    if not cm.empty:
        render_entity_drilldown(engine, days, unit_id, "국가", list(cm.index))

    st.markdown("##### 기업 × 기술영역")
    km = cached_tech_matrix(engine, days, unit_id, "기업", 8)
    _matrix_heatmap(km, "")
    if not km.empty:
        render_entity_drilldown(engine, days, unit_id, "기업", list(km.index))


def render_country_company(engine, days: int, unit_id):
    """국가 매트릭스 + 기업 추적 뷰. extracted_keywords의 국가/기업 필드 집계."""
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("#### 국가별 동향")
        country_df = cached_country_counts(engine, days, unit_id)
        if country_df.empty:
            st.info(f"국가 데이터 없음 — 최근 {days}일 분석 기사에 target_countries 필드가 없습니다.")
        else:
            st.caption(f"최근 {days}일 · 분석 기사 기준 상위 {min(15, len(country_df))}개국")
            fig = px.bar(
                country_df.head(15).iloc[::-1],
                x="count", y="country", orientation="h",
                labels={"count": "기사 수", "country": "국가"},
            )
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
    with cc2:
        st.markdown("#### 기업 추적")
        company_df = cached_company_counts(engine, days, unit_id, 15)
        if company_df.empty:
            st.info(f"기업 데이터 없음 — 최근 {days}일 분석 기사에 related_companies 필드가 없습니다.")
        else:
            st.caption(f"최근 {days}일 · 분석 기사 기준 상위 {min(15, len(company_df))}개 기업")
            fig = px.bar(
                company_df.head(15).iloc[::-1],
                x="count", y="company", orientation="h",
                labels={"count": "기사 수", "company": "기업"},
            )
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)


def render_suggested_questions(keywords: pd.DataFrame, entities: pd.DataFrame):
    base_terms = []
    if not keywords.empty:
        base_terms.extend(keywords["키워드"].dropna().astype(str).head(3).tolist())
    if not entities.empty:
        base_terms.extend(entities["엔티티"].dropna().astype(str).head(2).tolist())
    if not base_terms:
        base_terms = ["AI-RAN", "NTN", "6G", "양자통신"]

    # 동적 질문 (키워드/엔티티 기반)
    dynamic_questions = [
        f"최근 {base_terms[0]} 이슈의 표준화 시사점은?",
        f"{base_terms[min(1, len(base_terms)-1)]} 관련 주요 기업과 국가는?",
        f"{base_terms[min(2, len(base_terms)-1)]} 동향에서 TTA가 우선 검토할 점은?",
        "최근 90일간 긴급도가 높은 표준화 대응 후보를 정리해줘",
    ]
    # TTA 특화 고정 질문 (항상 노출)
    fixed_questions = [
        "TTA가 선제적으로 검토해야 할 6G·NTN 관련 표준화 이슈는?",
        "최근 국제 표준화 회의체(3GPP·ITU·IEEE) 동향에서 국내 대응이 필요한 항목은?",
    ]
    questions = dynamic_questions + fixed_questions

    # 3열 2행 배치 (6개)
    for row_start in range(0, len(questions), 3):
        cols = st.columns(3)
        for offset, question in enumerate(questions[row_start:row_start + 3]):
            idx = row_start + offset
            if cols[offset].button(question, key=f"home_question_{idx}", use_container_width=True):
                st.session_state["portal_query"] = question
                st.toast("질문형 분석실 입력창에 추천 질문을 넣었습니다.")


def render_home(engine, stats: dict):
    raw_df = fetch_articles(engine, days=365, analyzed_only=True, limit=2500)
    # ICT 관련성 필터 — 비ICT 기사 제거 (min_score=3)
    full_df = filter_home_articles(raw_df, min_score=3)
    if full_df.empty:
        full_df = raw_df  # fallback: 데이터 부족 시 필터 미적용
    window_days, recent_df, baseline_df = choose_home_window(full_df)
    keywords = trending_keywords(recent_df, baseline_df, limit=12)
    entities = new_entities(recent_df, baseline_df, limit=12)
    # Executive Brief 6장 — 오늘(가장 최근 수집일) 분석 뉴스에서 우선 선정.
    # 9시 파이프라인이 그날치 기사를 분석하면 그 풀에서 5축+다양성으로 6건이 갱신된다.
    daily_pool = select_daily_pool(full_df, min_articles=8)
    board = issue_board(daily_pool, limit=6, unit_names=UNIT_NAMES, diversify=True)
    if len(board) < 6:  # 오늘 분석분이 적으면 최근 윈도로 보강
        board = issue_board(
            recent_df if not recent_df.empty else full_df,
            limit=6, unit_names=UNIT_NAMES, diversify=True,
        )
    brief_day = daily_pool_label(daily_pool)
    unit_summary = unit_issue_summary(recent_df if not recent_df.empty else full_df, UNIT_NAMES, limit_per_unit=2)
    reports, report_source = fetch_report_artifacts(engine)

    st.markdown("### 인텔리전스 홈")
    ict_ratio = f"ICT 필터 후 {len(full_df):,} / 원본 {len(raw_df):,}건"
    st.caption(
        f"최근 {window_days}일 기준 실데이터 브리핑 · {ict_ratio} · "
        f"DB: {'PostgreSQL/Supabase' if is_postgres(engine) else 'SQLite'}"
    )

    # ── 오늘의 Executive Brief — 반드시 봐야 할 6개 (최상단) ──
    st.markdown('<div class="home-section-title">오늘의 Executive Brief</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="home-section-sub">{esc(brief_day)} 분석 뉴스에서 선정한 6개 이슈 · '
        f'영향도·긴급도·ICT·표준화·최신성 5축 + 다양성 · 국가/기업/기술/표준 한눈에</div>',
        unsafe_allow_html=True,
    )
    render_executive_brief_top(board, count=6)

    # ── KPI strip ────────────────────────────────────
    render_kpi_strip(stats, board, keywords, reports)

    # ── 핵심 시그널 + 키워드 바 (나란히) ───────────────
    st.markdown('<div class="home-section-title">오늘의 핵심 시그널</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="home-section-sub">RAG 기반 AI 요약 · 영향도·긴급도·ICT 관련성 종합 1순위 이슈</div>',
        unsafe_allow_html=True,
    )
    # RAG 요약 — 하루 단위 캐시 (첫 로드만 GPT 호출)
    top_issue_title = str(board.iloc[0].get("이슈 후보", "")) if not board.empty else ""
    rag_date_key = datetime.now().strftime("%Y-%m-%d")
    rag_summary = build_rag_top_signal(engine, top_issue_title, rag_date_key)

    sig_col, kw_col = st.columns([13, 9])
    with sig_col:
        render_issue_cards(board, rag_summary=rag_summary)
    with kw_col:
        render_keyword_bars(keywords)

    # ── 단별 브리핑 ───────────────────────────────────
    st.markdown('<div class="home-section-title">단별 브리핑</div>', unsafe_allow_html=True)
    render_unit_briefs(unit_summary)

    # ── 국가·기업 표준화 포지션 매트릭스 ───────────────
    st.markdown('<div class="home-section-title">국가·기업 표준화 포지션 매트릭스</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="home-section-sub">최근 90일 · 국가/기업이 어느 기술영역에서 활동하는지 · 빈칸 = TTA 기여 기회</div>',
        unsafe_allow_html=True,
    )
    render_standardization_matrix(engine, 90, None)

    # ── 즉시 검토 필요 배너 ───────────────────────────
    render_urgent_section(board)

    # ── 신규 엔티티 ───────────────────────────────────
    st.markdown('<div class="home-section-title">신규 등장 엔티티</div>', unsafe_allow_html=True)
    render_chip_cloud(entities, "엔티티", "최근등장", "새로 등장한 엔티티가 아직 감지되지 않았습니다.")

    # ── 최신 기사 / 보고서 ────────────────────────────
    render_latest_lists(recent_df, reports)
    st.caption(f"보고서 목록 출처: {report_source}")

    # ── 질문형 분석 추천 ──────────────────────────────
    st.markdown('<div class="home-section-title">질문형 분석 추천</div>', unsafe_allow_html=True)
    st.markdown('<div class="home-section-sub">버튼을 누르면 질문형 분석실 입력창에 질문이 준비됩니다.</div>', unsafe_allow_html=True)
    render_suggested_questions(keywords, entities)


def refresh_caches_if_data_changed(stats: dict):
    """9시 파이프라인이 새 기사를 분석하면 집계 캐시를 비워 Executive Brief·레이더가 갱신되게 한다.
    신호 = 분석완료 기사 수 + 날짜. 둘 중 하나라도 바뀌면 2시간 TTL을 기다리지 않고 즉시 무효화."""
    signature = f"{stats.get('analyzed', 0)}|{datetime.now():%Y-%m-%d}"
    if st.session_state.get("_data_signature") == signature:
        return
    for cached_fn in (
        cached_country_counts, cached_company_counts, cached_issue_timeline,
        cached_cluster_counts, cached_cluster_detail, cached_tech_matrix,
        build_rag_top_signal,
    ):
        try:
            cached_fn.clear()
        except Exception:
            pass
    st.session_state["_data_signature"] = signature


def main():
    embed_mode = is_embed_mode()
    apply_portal_style(embed_mode)

    if not check_staff_access(embed_mode=embed_mode):
        st.stop()

    engine = cached_engine()
    stats = fetch_stats(engine)
    refresh_caches_if_data_changed(stats)
    sources = fetch_sources(engine)
    render_header(stats, embed_mode)

    with st.sidebar:
        st.header("데이터 연결")
        st.write("DB:", "PostgreSQL/Supabase" if is_postgres(engine) else "SQLite")
        st.metric("전체 기사", f"{stats.get('articles', 0):,}")
        st.metric("분석 완료", f"{stats.get('analyzed', 0):,}")
        st.metric("임베딩", f"{stats.get('embeddings', 0):,}")

    tab_home, tab_radar, tab_board, tab_reports, tab_map, tab_qa = st.tabs([
        "홈",
        "오늘의 레이더",
        "표준화 대응 보드",
        "보고서 보관함",
        "이슈 맵",
        "질문형 분석실",
    ])

    with tab_home:
        render_home(engine, stats)

    with tab_radar:
        st.subheader("오늘의 레이더")
        rc1, rc2, rc3 = st.columns([1, 1, 2])
        radar_days = rc1.selectbox("레이더 기간", [3, 7, 14, 30], index=1)
        radar_unit_label = rc2.selectbox("단 필터", list(UNIT_OPTIONS.keys()), key="radar_unit")
        rc3.caption("최근 기간과 이전 기준기간을 비교해 급등 키워드와 새로 등장한 엔티티를 추정합니다.")
        radar_df = fetch_articles(
            engine,
            days=365,
            unit_id=UNIT_OPTIONS[radar_unit_label],
            analyzed_only=True,
            limit=2000,
        )
        recent_df, baseline_df = split_recent_baseline(radar_df, radar_days)
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("최근 분석 기사", f"{len(recent_df):,}")
        kpi2.metric("기준기간 기사", f"{len(baseline_df):,}")
        kpi3.metric("레이더 기간", f"{radar_days}일")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 급등 키워드")
            st.dataframe(trending_keywords(recent_df, baseline_df), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("#### 신규 등장 엔티티")
            st.dataframe(new_entities(recent_df, baseline_df), use_container_width=True, hide_index=True)

        st.markdown("#### 단별 추천 이슈")
        st.dataframe(
            unit_issue_summary(recent_df, UNIT_NAMES),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.markdown("### 국가·기업 동향")
        nc1, nc2 = st.columns([1, 3])
        cc_days = nc1.selectbox("집계 기간", [30, 90, 180, 365], index=1, key="cc_days")
        if nc2.button("데이터 새로고침", key="cc_refresh"):
            cached_country_counts.clear()
            cached_company_counts.clear()
            cached_issue_timeline.clear()
            cached_cluster_counts.clear()
            st.rerun()
        render_country_company(engine, cc_days, UNIT_OPTIONS[radar_unit_label])

        st.divider()
        st.markdown("### 이슈 타임라인")
        st.caption("기술 키워드의 주차별 등장 추이와 급등/소강 단계 (key_technologies 기준)")
        render_issue_timeline(engine, cc_days, UNIT_OPTIONS[radar_unit_label])

        st.divider()
        st.markdown("### 기사 클러스터")
        st.caption("임베딩 기반 K-means 군집 분포 (cluster_articles.py 배치 결과)")
        render_clusters(engine, cc_days, UNIT_OPTIONS[radar_unit_label])

    with tab_board:
        st.subheader("표준화 대응 보드")
        bc1, bc2, bc3 = st.columns(3)
        board_days = bc1.selectbox("대응 검토 기간", [7, 14, 30, 90, 180, 365], index=2)
        board_unit_label = bc2.selectbox("단", list(UNIT_OPTIONS.keys()), key="board_unit")
        board_limit = bc3.slider("후보 수", min_value=10, max_value=50, value=25, step=5)
        board_df = fetch_articles(
            engine,
            days=board_days,
            unit_id=UNIT_OPTIONS[board_unit_label],
            analyzed_only=True,
            limit=1000,
        )
        board = issue_board(board_df, limit=board_limit, unit_names=UNIT_NAMES)
        if board.empty:
            st.info("대응 후보가 없습니다. 기간을 넓히거나 단 필터를 해제해 보세요.")
        else:
            # 에디터는 안정된 컬럼 집합만 노출 (리본용 분류 컬럼은 숨김, 표준화 연계성은 표시)
            admin_cols = [
                "이슈 후보", "담당 단", "검토 상태", "영향도", "긴급도", "표준화 연계성",
                "종합점수", "영향등급", "왜 중요한가", "TTA 대응과제",
                "관련 엔티티", "관련 기사", "출처", "권장 조치", "조치 메모",
            ]
            board = board[[c for c in admin_cols if c in board.columns]]
            editable_board, action_source = merge_issue_actions(board, engine)
            st.caption(f"대응 상태 출처: {action_source}")
            edited_board = st.data_editor(
                editable_board,
                column_config={
                    "관련 기사": st.column_config.LinkColumn("관련 기사"),
                    "영향도": st.column_config.ProgressColumn("영향도", min_value=0, max_value=10),
                    "긴급도": st.column_config.ProgressColumn("긴급도", min_value=0, max_value=10),
                    "표준화 연계성": st.column_config.ProgressColumn("표준화 연계성", min_value=0, max_value=10),
                    "종합점수": st.column_config.NumberColumn("종합점수", format="%.2f"),
                    "검토 상태": st.column_config.SelectboxColumn("검토 상태", options=STATUS_OPTIONS),
                    "조치 메모": st.column_config.TextColumn("조치 메모"),
                },
                disabled=["이슈 후보", "영향도", "긴급도", "표준화 연계성", "종합점수", "관련 엔티티", "관련 기사", "출처", "권장 조치", "updated_at"],
                use_container_width=True,
                hide_index=True,
                key="issue_board_editor",
            )
            st.caption("영향도·긴급도·ICT·표준화·최신성 5축 가중합(종합점수) 기반 1차 휴리스틱입니다. 표준화 연계성은 TTA 미션 가중이 높습니다.")
            if st.button("검토 상태 저장"):
                target, detail = save_issue_actions(
                    engine,
                    edited_board,
                    updated_by=st.session_state.get("staff_email", ""),
                )
                st.success(f"저장 완료: {target} ({detail})")

    with tab_reports:
        st.subheader("보고서 보관함")
        reports, report_source = fetch_report_artifacts(engine)
        st.caption(f"산출물 목록 출처: {report_source}")
        if reports.empty:
            st.info("등록된 보고서/Excel 산출물이 없습니다.")
        else:
            fc1, fc2, fc3 = st.columns(3)
            type_filter = fc1.selectbox("유형", ["전체"] + sorted(reports["report_type"].dropna().astype(str).unique().tolist()))
            status_filter = fc2.selectbox("상태", ["전체"] + sorted(reports["status"].dropna().astype(str).unique().tolist()))
            text_filter = fc3.text_input("제목 검색", "")
            view = reports.copy()
            if type_filter != "전체":
                view = view[view["report_type"] == type_filter]
            if status_filter != "전체":
                view = view[view["status"] == status_filter]
            if text_filter.strip():
                view = view[view["title"].astype(str).str.contains(text_filter.strip(), case=False, na=False)]
            r1, r2, r3 = st.columns(3)
            r1.metric("등록 산출물", f"{len(reports):,}")
            r2.metric("게시 완료", f"{(reports['status'] == 'published').sum():,}")
            r3.metric("현재 표시", f"{len(view):,}")

            if view.empty:
                st.info("필터 조건에 맞는 산출물이 없습니다.")
            else:
                render_report_cards(view)

                with st.expander("표 형태로 보기"):
                    st.dataframe(
                        view,
                        column_config={
                            "google_doc_url": st.column_config.LinkColumn("Google Docs"),
                            "excel_file_url": st.column_config.LinkColumn("Excel"),
                            "source_article_count": st.column_config.NumberColumn("기사 수"),
                        },
                        use_container_width=True,
                        hide_index=True,
                    )

    with tab_map:
        st.subheader("이슈 맵")
        st.caption("기업/기술/국가/표준 키워드의 공출현 관계를 이용해 중심 엔티티와 주요 클러스터 후보를 확인합니다.")
        gc1, gc2, gc3 = st.columns(3)
        graph_days = gc1.selectbox("분석 기간", [7, 30, 90, 180, 365, 9999], index=4, key="graph_days")
        graph_unit_label = gc2.selectbox("단 필터", list(UNIT_OPTIONS.keys()), key="graph_unit")
        min_weight = gc3.slider("최소 공출현", 1, 5, 1)
        graph_df = fetch_articles(
            engine,
            days=graph_days,
            unit_id=UNIT_OPTIONS[graph_unit_label],
            analyzed_only=True,
            limit=1000,
        )
        nodes, edges = build_edges(graph_df, min_weight=min_weight)
        st.markdown("#### GraphRAG 요약")
        st.text(graph_summary(nodes, edges))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 중심 엔티티")
            if nodes.empty:
                st.info("엔티티가 없습니다.")
            else:
                st.dataframe(nodes.sort_values("count", ascending=False).head(50), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("#### 주요 클러스터 후보")
            if edges.empty:
                st.info("관계가 없습니다.")
            else:
                st.dataframe(edges.sort_values("weight", ascending=False).head(50), use_container_width=True, hide_index=True)

    with tab_qa:
        st.subheader("질문형 분석실")
        render_quick_queries()
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        query = c1.text_input(
            "질문 또는 키워드",
            value=st.session_state.get("portal_query", ""),
            placeholder="예: 최근 NTN 표준화 이슈를 정리해줘",
        )
        days = c2.selectbox("기간", [7, 14, 30, 90, 180, 365, 9999], index=5)
        unit_label = c3.selectbox("단", list(UNIT_OPTIONS.keys()))
        source = c4.selectbox("출처", [""] + sources)
        top_k = st.slider("검색 결과 수", min_value=5, max_value=50, value=20, step=5)
        analyzed_only = st.checkbox("분석 완료 기사만", value=True)

        if st.button("검색", type="primary"):
            unit_id = UNIT_OPTIONS[unit_label]
            if query.strip():
                results, mode = hybrid_search(
                    engine,
                    query.strip(),
                    days=days,
                    unit_id=unit_id,
                    top_k=top_k,
                    analyzed_only=analyzed_only,
                )
                if source and not results.empty:
                    results = results[results["source"] == source]
                st.session_state["last_results"] = results
                st.session_state["last_query"] = query.strip()
                st.session_state["last_mode"] = mode
            else:
                results = fetch_articles(
                    engine,
                    days=days,
                    source=source,
                    unit_id=UNIT_OPTIONS[unit_label],
                    analyzed_only=analyzed_only,
                    limit=top_k,
                )
                st.session_state["last_results"] = results
                st.session_state["last_query"] = ""
                st.session_state["last_mode"] = "sql"

        results = st.session_state.get("last_results", pd.DataFrame())
        mode = st.session_state.get("last_mode", "")
        if mode:
            st.caption(f"검색 방식: {mode}")
        if results.empty:
            st.warning("결과가 없습니다. 기간을 90일 이상으로 넓히거나, 단/출처 필터를 해제하거나, '분석 완료 기사만'을 꺼보세요.")
        article_table(results)

        if not results.empty and st.session_state.get("last_query"):
            if st.button("근거 기반 답변 생성"):
                with st.spinner("답변 생성 중"):
                    answer = build_answer(st.session_state["last_query"], results)
                st.markdown("#### 답변")
                st.write(answer)
                st.markdown("#### 근거 기사")
                for _, row in results.head(8).iterrows():
                    st.markdown(f"- [{row.get('title', '')}]({row.get('link', '')}) - {row.get('source', '')}")


if __name__ == "__main__":
    main()
