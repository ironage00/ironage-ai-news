import os
from datetime import datetime

import pandas as pd
import streamlit as st

from artifact_utils import fetch_report_artifacts
from db import fetch_articles, fetch_sources, fetch_stats, get_engine, is_postgres
from graph_utils import build_edges, graph_summary
from radar_utils import issue_board, new_entities, split_recent_baseline, trending_keywords, unit_issue_summary
from search import build_answer, hybrid_search
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

    tab_radar, tab_board, tab_reports, tab_map, tab_qa = st.tabs([
        "오늘의 레이더",
        "표준화 대응 보드",
        "보고서 보관함",
        "이슈 맵",
        "질문형 분석실",
    ])

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
