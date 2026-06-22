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
        :root {{
            --tta-navy: #071427;
            --tta-blue: #0e5aa7;
            --tta-cyan: #0f766e;
            --tta-line: #dbe3ee;
            --tta-soft: #f6f8fb;
            --tta-text: #0f172a;
        }}
        html, body, [data-testid="stAppViewContainer"] {{
            background: #f6f8fb;
            color: var(--tta-text);
        }}
        .block-container {{
            padding-top: {top_padding};
            padding-bottom: 2rem;
            max-width: 1320px;
        }}
        div[data-testid="stTabs"] button {{
            font-weight: 800;
        }}
        div[data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid var(--tta-line);
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 10px 22px rgba(15,23,42,.045);
        }}
        .portal-hero {{
            border: 1px solid #1e3a5f;
            border-radius: 18px;
            padding: 26px 28px;
            background: linear-gradient(135deg, #071427 0%, #12396c 58%, #0f766e 100%);
            color: #ffffff;
            margin-bottom: 16px;
            box-shadow: 0 18px 42px rgba(15,23,42,.14);
        }}
        .portal-hero h1 {{
            margin: 0 0 6px 0;
            font-size: 1.85rem;
            letter-spacing: 0;
            font-weight: 900;
        }}
        .portal-hero p {{
            margin: 0;
            color: #d7e6f5;
            font-size: 0.95rem;
            line-height: 1.65;
        }}
        .stDataFrame, div[data-testid="stDataFrame"] {{
            border-radius: 12px;
            overflow: hidden;
        }}
        div[data-testid="stAlert"] {{
            border-radius: 12px;
        }}
        .quick-query-panel {{
            border: 1px solid var(--tta-line);
            border-radius: 14px;
            background: #ffffff;
            padding: 14px 14px 4px 14px;
            margin-bottom: 10px;
            box-shadow: 0 10px 22px rgba(15,23,42,.04);
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
    st.markdown(
        """
        <div class="portal-hero">
          <h1>TTA Intelligence Radar v0.1</h1>
          <p>급등 이슈, 표준화 대응 후보, 관계 맵, 근거 기반 질의응답을 한 곳에서 보는 직원용 인텔리전스 화면입니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not embed_mode:
        st.caption("별도 대시보드 프로그램입니다. 기존 운영 코드는 수정하거나 import하지 않습니다.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 기사", f"{stats.get('articles', 0):,}")
    m2.metric("분석 완료", f"{stats.get('analyzed', 0):,}")
    m3.metric("임베딩", f"{stats.get('embeddings', 0):,}")
    missing = max(stats.get("analyzed", 0) - stats.get("embeddings", 0), 0)
    m4.metric("임베딩 누락", f"{missing:,}")


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
