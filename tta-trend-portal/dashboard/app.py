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


def render_executive_brief_top(board: pd.DataFrame):
    """오늘 반드시 봐야 할 6개 이슈 — 홈 최상단 카드.
    제목·영향등급·왜 중요한가·관련 기술/표준·TTA 대응·분석실 버튼."""
    if board.empty:
        st.info("오늘의 핵심 이슈를 만들 분석 기사가 아직 부족합니다.")
        return
    top6 = board.head(6)
    for row_start in range(0, len(top6), 3):
        cols = st.columns(3)
        for offset, (_, row) in enumerate(top6.iloc[row_start:row_start + 3].iterrows()):
            i = row_start + offset
            level = str(row.get("영향등급", "") or "")
            why = str(row.get("왜 중요한가", "") or "")
            tta = str(row.get("TTA 대응과제", "") or "")
            ents = str(row.get("관련 엔티티", "") or "")
            with cols[offset]:
                with st.container(border=True):
                    st.markdown(
                        impact_badge_html(level)
                        + f"  <span class='meta-pill'>긴급도 {esc(row.get('긴급도'))}/10</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**{esc(row.get('이슈 후보'), 90)}**")
                    if why:
                        st.caption("왜 중요한가: " + esc(why, 160))
                    if ents:
                        st.caption("관련 기술/표준: " + esc(ents, 80))
                    if tta:
                        st.markdown(
                            f"<div style='font-size:0.82rem;color:#0369a1;'>TTA 대응: {esc(tta, 130)}</div>",
                            unsafe_allow_html=True,
                        )
                    bc1, bc2 = st.columns(2)
                    bc1.link_button("자세히 보기", str(row.get("관련 기사", "") or "#"), use_container_width=True)
                    if bc2.button("분석실로", key=f"exec_brief_qa_{i}", use_container_width=True):
                        st.session_state["portal_query"] = str(row.get("이슈 후보", ""))
                        st.toast("질문형 분석실 입력창에 준비했습니다. QA 탭으로 이동하세요.")


@st.cache_data(ttl=7200, show_spinner=False)
def cached_country_counts(_engine, days: int, unit_id):
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return country_counts(df)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_company_counts(_engine, days: int, unit_id, top_n: int):
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return company_counts(df, top_n=top_n)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_issue_timeline(_engine, days: int, unit_id, top_n: int):
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return issue_timeline(df, top_n=top_n)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_cluster_counts(_engine, days: int, unit_id):
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return cluster_counts(df)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_cluster_detail(_engine, days: int, unit_id, top_n: int = 8):
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    return cluster_detail(df, top_n_clusters=top_n)


def render_clusters(engine, days: int, unit_id):
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

    details = cached_cluster_detail(engine, days, unit_id, 8)
    for detail in details:
        with st.expander(f"📁 {detail['label']}  ·  {detail['count']}건", expanded=False):
            meta = st.columns(2)
            with meta[0]:
                if detail["technologies"]:
                    st.caption("핵심 키워드: " + ", ".join(detail["technologies"]))
                if detail["companies"]:
                    st.caption("주요 기업: " + ", ".join(detail["companies"]))
                if detail["countries"]:
                    st.caption("주요 국가: " + ", ".join(detail["countries"]))
            with meta[1]:
                if detail["sources"]:
                    st.caption("주요 출처: " + ", ".join(detail["sources"]))
                if detail["standards"]:
                    st.caption("표준화 포인트: " + " / ".join(detail["standards"]))
            st.markdown("**대표 기사**")
            for article in detail["articles"]:
                st.markdown(f"- [{esc(article['title'], 90)}]({article['link']}) · {esc(article['source'], 30)}")


def render_issue_timeline(engine, days: int, unit_id):
    tl = cached_issue_timeline(engine, days, unit_id, 8)
    if tl.empty:
        st.info(f"타임라인 데이터 없음 — 최근 {days}일 분석 기사에 key_technologies 필드가 없습니다.")
        return

    latest_stage = tl.groupby("technology")["stage"].last()
    surging = [tech for tech, stage in latest_stage.items() if stage == "급등"]
    fading = [tech for tech, stage in latest_stage.items() if stage == "소강"]
    sc1, sc2 = st.columns(2)
    sc1.caption("🔺 급등: " + (", ".join(surging) if surging else "없음"))
    sc2.caption("🔻 소강: " + (", ".join(fading) if fading else "없음"))

    fig = px.line(
        tl,
        x="week",
        y="count",
        color="technology",
        markers=True,
        labels={"week": "주차", "count": "기사 수", "technology": "기술"},
    )
    fig.update_layout(height=440, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="기술")
    st.plotly_chart(fig, use_container_width=True)


@st.cache_data(ttl=7200, show_spinner=False)
def cached_tech_matrix(_engine, days: int, unit_id, entity_label: str, top_entities: int):
    df = fetch_articles(_engine, days=days, unit_id=unit_id, analyzed_only=True, limit=3000)
    normalize = COUNTRY_NORMALIZE if entity_label == "국가" else COMPANY_NORMALIZE
    return entity_tech_matrix(df, entity_label, normalize, top_entities=top_entities)


def _matrix_heatmap(matrix: pd.DataFrame, title: str):
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
    fig.update_layout(
        height=40 * len(matrix) + 120,
        margin=dict(l=10, r=10, t=30, b=10),
        coloraxis_showscale=False,
        title=title,
    )
    fig.update_xaxes(side="top")
    st.plotly_chart(fig, use_container_width=True)


def _tta_implication(detail: dict, entity_label: str) -> str:
    areas = detail.get("top_areas", [])
    if not areas:
        return "관련 기술영역 신호가 아직 약함 — 모니터링 유지."
    area_txt = " · ".join(areas[:3])
    subject = "표준화 동향" if entity_label == "국가" else "기술·표준 활동"
    return f"{area_txt} 영역에서 활발 ({detail['article_count']}건). 관련 {subject} 추적 권장."


def render_entity_drilldown(engine, days: int, unit_id, entity_label: str, options: list[str]):
    if not options:
        return
    picked = st.selectbox(f"{entity_label} 선택", options, key=f"drill_{entity_label}")
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
        for article in detail["articles"]:
            st.markdown(f"- [{esc(article['title'], 90)}]({article['link']}) · {esc(article['source'], 30)}")


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
    board = issue_board(recent_df if not recent_df.empty else full_df, limit=12, unit_names=UNIT_NAMES)

    st.markdown("### 인텔리전스 홈")
    ict_ratio = f"ICT 필터 후 {len(full_df):,} / 원본 {len(raw_df):,}건"
    st.caption(
        f"최근 {window_days}일 기준 실데이터 브리핑 · {ict_ratio} · "
        f"DB: {'PostgreSQL/Supabase' if is_postgres(engine) else 'SQLite'}"
    )

    st.markdown('<div class="home-section-title">오늘의 Executive Brief</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="home-section-sub">오늘 반드시 봐야 할 6개 이슈 · 영향등급·왜 중요한가·TTA 대응</div>',
        unsafe_allow_html=True,
    )
    render_executive_brief_top(board)

    st.markdown('<div class="home-section-title">국가·기업 표준화 포지션 매트릭스</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="home-section-sub">최근 90일 · 국가/기업이 어느 기술영역에서 활동하는지 · 빈칸 = TTA 기여 기회</div>',
        unsafe_allow_html=True,
    )
    render_standardization_matrix(engine, 90, None)


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

    tab_home, tab_radar, tab_reports, tab_qa = st.tabs([
        "홈",
        "오늘의 레이더",
        "보고서 보관함",
        "질문형 분석실",
    ])

    with tab_home:
        render_home(engine, stats)

    with tab_radar:
        st.subheader("오늘의 레이더")
        rc1, rc2 = st.columns([1, 3])
        radar_unit_label = rc1.selectbox("단 필터", list(UNIT_OPTIONS.keys()), key="radar_unit")
        rc2.caption("국가·기업 동향, 이슈 타임라인, 기사 클러스터를 중심으로 레이더를 확인합니다.")

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
