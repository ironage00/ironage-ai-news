import html
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from artifact_utils import fetch_report_artifacts
from db import fetch_articles, fetch_sources, fetch_stats, get_engine, is_postgres
from graph_utils import build_edges, graph_summary
from radar_utils import filter_home_articles, issue_board, new_entities, split_recent_baseline, trending_keywords, unit_issue_summary
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
    "표준진흥단": 2,
    "AI융합단": 3,
    "전파네트워크단": 4,
}

UNIT_NAMES = {value: label for label, value in UNIT_OPTIONS.items() if value is not None}

UNIT_COLORS = {
    "표준기획단": "#0284c7",
    "표준진흥단": "#059669",
    "AI융합단": "#7c3aed",
    "전파네트워크단": "#b45309",
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


def render_issue_cards(board: pd.DataFrame):
    if board.empty:
        st.info("표준화 대응 후보를 만들 수 있는 분석 기사가 아직 부족합니다.")
        return

    top = board.iloc[0]
    st.markdown(
        f"""
        <div class="briefing-card dark" style="margin-bottom:12px;">
          <div class="briefing-eyebrow">Top Signal</div>
          <div class="briefing-title">{esc(top.get("이슈 후보"), 180)}</div>
          <div class="briefing-meta">
            <span class="meta-pill">영향도 {esc(top.get("영향도"))}/10</span>
            <span class="meta-pill">긴급도 {esc(top.get("긴급도"))}/10</span>
            <span class="meta-pill">{esc(top.get("담당 단"))}</span>
          </div>
          <div class="briefing-body">{esc(top.get("권장 조치"), 260)}</div>
          <a class="briefing-link" href="{esc(top.get("관련 기사"))}" target="_blank">근거 기사 열기</a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    html_parts = ['<div class="mini-grid">']
    for _, row in board.head(4).iterrows():
        unit_raw = str(row.get("담당 단", ""))
        dot_color = UNIT_COLORS.get(unit_raw, "#64748b")
        html_parts.append(f"""
        <div class="mini-card">
          <div class="unit-card-header" style="margin-bottom:4px;">
            <div class="unit-dot" style="background:{dot_color};"></div>
            <div class="mini-label">{esc(unit_raw)}</div>
          </div>
          <div class="mini-value">{esc(row.get("이슈 후보"), 58)}</div>
          <div class="mini-desc">영향도 {esc(row.get("영향도"))}/10 · 긴급도 {esc(row.get("긴급도"))}/10<br>{esc(row.get("출처"), 35)}</div>
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


def render_suggested_questions(keywords: pd.DataFrame, entities: pd.DataFrame):
    base_terms = []
    if not keywords.empty:
        base_terms.extend(keywords["키워드"].dropna().astype(str).head(3).tolist())
    if not entities.empty:
        base_terms.extend(entities["엔티티"].dropna().astype(str).head(2).tolist())
    if not base_terms:
        base_terms = ["AI-RAN", "NTN", "6G", "양자통신"]

    questions = [
        f"최근 {base_terms[0]} 이슈의 표준화 시사점은?",
        f"{base_terms[min(1, len(base_terms)-1)]} 관련 주요 기업과 국가는?",
        f"{base_terms[min(2, len(base_terms)-1)]} 동향에서 TTA가 우선 검토할 점은?",
        "최근 90일간 긴급도가 높은 표준화 대응 후보를 정리해줘",
    ]
    cols = st.columns(4)
    for idx, question in enumerate(questions):
        if cols[idx].button(question, key=f"home_question_{idx}", use_container_width=True):
            st.session_state["portal_query"] = question
            st.toast("질문형 분석실 입력창에 추천 질문을 넣었습니다.")


def render_home(engine, stats: dict):
    raw_df = fetch_articles(engine, days=365, analyzed_only=True, limit=2500)
    full_df = filter_home_articles(raw_df)
    if full_df.empty:
        full_df = raw_df
    window_days, recent_df, baseline_df = choose_home_window(full_df)
    keywords = trending_keywords(recent_df, baseline_df, limit=12)
    entities = new_entities(recent_df, baseline_df, limit=12)
    board = issue_board(recent_df if not recent_df.empty else full_df, limit=8, unit_names=UNIT_NAMES)
    unit_summary = unit_issue_summary(recent_df if not recent_df.empty else full_df, UNIT_NAMES, limit_per_unit=2)
    reports, report_source = fetch_report_artifacts(engine)

    st.markdown("### 인텔리전스 홈")
    st.caption(f"최근 {window_days}일 기준 실데이터 브리핑입니다. DB: {'PostgreSQL/Supabase' if is_postgres(engine) else 'SQLite'}")

    # ── KPI strip ────────────────────────────────────
    render_kpi_strip(stats, board, keywords, reports)

    # ── 핵심 시그널 + 키워드 바 (나란히) ───────────────
    st.markdown('<div class="home-section-title">오늘의 핵심 시그널</div>', unsafe_allow_html=True)
    st.markdown('<div class="home-section-sub">AI 분석문, 키워드, 최신성, 표준화 관련도를 조합해 직원이 먼저 볼 이슈를 띄웁니다.</div>', unsafe_allow_html=True)
    sig_col, kw_col = st.columns([13, 9])
    with sig_col:
        render_issue_cards(board)
    with kw_col:
        render_keyword_bars(keywords)

    # ── 단별 브리핑 ───────────────────────────────────
    st.markdown('<div class="home-section-title">단별 브리핑</div>', unsafe_allow_html=True)
    render_unit_briefs(unit_summary)

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


def main():
    embed_mode = is_embed_mode()
    apply_portal_style(embed_mode)

    if not check_staff_access(embed_mode=embed_mode):
        st.stop()

    engine = cached_engine()
    stats = fetch_stats(engine)
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
            editable_board, action_source = merge_issue_actions(board, engine)
            st.caption(f"대응 상태 출처: {action_source}")
            edited_board = st.data_editor(
                editable_board,
                column_config={
                    "관련 기사": st.column_config.LinkColumn("관련 기사"),
                    "영향도": st.column_config.ProgressColumn("영향도", min_value=0, max_value=10),
                    "긴급도": st.column_config.ProgressColumn("긴급도", min_value=0, max_value=10),
                    "검토 상태": st.column_config.SelectboxColumn("검토 상태", options=STATUS_OPTIONS),
                    "조치 메모": st.column_config.TextColumn("조치 메모"),
                },
                disabled=["이슈 후보", "영향도", "긴급도", "관련 엔티티", "관련 기사", "출처", "권장 조치", "updated_at"],
                use_container_width=True,
                hide_index=True,
                key="issue_board_editor",
            )
            st.caption("영향도/긴급도는 기사 분석문, 표준화 키워드, 최신성, 품질점수 기반의 1차 휴리스틱입니다.")
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
