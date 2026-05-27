"""
intelligence_widgets.py — 인텔리전스 키워드 분석 섹션 공유 렌더러
=================================================================
홈 페이지와 운영 대시보드 양쪽에서 동일한 키워드 분석·인텔리전스 매트릭스를
중복 없이 렌더링하기 위한 모듈입니다.

Usage:
    from intelligence_widgets import render_keyword_intelligence
    render_keyword_intelligence(key_prefix="home")   # 홈 페이지
    render_keyword_intelligence(key_prefix="dash")   # 운영 대시보드
"""

import json
import traceback
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st


def render_keyword_intelligence(key_prefix: str = "dash") -> None:
    """AI 키워드 분析 + 인텔리전스 매트릭스 + 모델 품질 렌더링.

    Args:
        key_prefix: Streamlit 위젯 키 충돌 방지용 접두어.
                    홈 페이지 → "home", 운영 대시보드 → "dash".
    """
    import datetime as _dt

    # 지연 임포트 (news_engine 의존성)
    from news_engine import load_news_from_db, get_db_session, NewsArticle

    st.markdown("---")
    st.markdown("#### 🤖 AI 추출 핵심 키워드 분析")

    col_refresh_ki, col_period_ki = st.columns([1, 3])
    with col_refresh_ki:
        if st.button("🔄 키워드 새로고침", key=f"{key_prefix}_refresh_kw", use_container_width=True):
            st.rerun()
    with col_period_ki:
        keyword_days = st.selectbox(
            "분析 기간",
            options=[7, 14, 30, 90],
            index=2,
            format_func=lambda x: f"최근 {x}일",
            key=f"{key_prefix}_kw_period",
        )

    try:
        _all_news = load_news_from_db(days=keyword_days)
        news_with_keywords = [n for n in _all_news if n.get("extracted_keywords")]

        st.info(f"📊 분析 대상: 최근 {keyword_days}일간 키워드 추출된 뉴스 {len(news_with_keywords)}개")

        if not news_with_keywords:
            st.warning(f"⚠️ 최근 {keyword_days}일간 키워드가 추출된 뉴스가 없습니다.")
            st.info("💡 뉴스를 먼저 분析하거나 기간을 늘려보세요.")
        else:
            st.success(f"✅ {len(news_with_keywords)}개 뉴스에서 키워드 발견!")

        all_keywords: list = []
        keyword_categories: Counter = Counter()
        importance_counts: Counter = Counter()
        all_companies: list = []
        all_technologies: list = []
        all_countries: list = []

        TECH_SYNONYMS = {
            "저궤도 위성통신": "위성통신", "저궤도": "위성통신",
            "satellite communications": "위성통신", "위성 통신": "위성통신",
            "생성형 ai": "AI", "genai": "AI", "인공지능": "AI",
            "생성형ai": "AI", "인공 지능": "AI",
            "6세대 이동통신": "6G", "sixth generation": "6G", "6세대 통신": "6G",
            "개방형 무선 접속망": "Open RAN", "오픈랜": "Open RAN",
            "oran": "Open RAN", "openran": "Open RAN",
            "사물인터넷": "IoT", "비지상 네트워크": "NTN", "비지상네트워크": "NTN",
        }

        for news in news_with_keywords:
            if news.get("extracted_keywords"):
                try:
                    keyword_data = json.loads(news["extracted_keywords"])
                    for kw in keyword_data.get("keywords", []):
                        term = kw.get("term", "")
                        if term:
                            all_keywords.append({
                                "term": term,
                                "category": kw.get("category", "기타"),
                                "importance": kw.get("importance", "medium"),
                            })
                            keyword_categories[kw.get("category", "기타")] += 1
                            importance_counts[kw.get("importance", "medium")] += 1

                    rel_companies = keyword_data.get("related_companies", [])
                    key_techs = keyword_data.get("key_technologies", [])
                    tgt_countries = keyword_data.get("target_countries", [])

                    if isinstance(rel_companies, list):
                        all_companies.extend([c for c in rel_companies if c])
                    if isinstance(key_techs, list):
                        for tech in key_techs:
                            if not tech:
                                continue
                            norm_tech = TECH_SYNONYMS.get(tech.lower(), tech)
                            all_technologies.append(norm_tech)
                    if isinstance(tgt_countries, list):
                        all_countries.extend([c for c in tgt_countries if c])
                except Exception:
                    continue

        # ── TOP 20 키워드 + 카테고리 분포 ─────────────────────────────────────
        if all_keywords:
            keyword_freq = Counter([kw["term"] for kw in all_keywords])
            top_keywords = keyword_freq.most_common(30)

            col_kw1, col_kw2 = st.columns(2)

            with col_kw1:
                st.markdown("**📊 TOP 20 키워드**")
                df_keywords = pd.DataFrame(top_keywords[:20], columns=["키워드", "빈도"])
                fig_keywords = px.bar(
                    df_keywords, x="빈도", y="키워드", orientation="h", title="",
                    color="빈도", color_continuous_scale="Viridis", text="빈도",
                )
                fig_keywords.update_layout(
                    height=500, yaxis={"categoryorder": "total ascending"}, showlegend=False,
                )
                fig_keywords.update_traces(textposition="outside")
                st.plotly_chart(fig_keywords, use_container_width=True)

            with col_kw2:
                st.markdown("**📂 카테고리별 분포**")
                df_categories = pd.DataFrame(
                    keyword_categories.most_common(), columns=["카테고리", "개수"]
                )
                fig_categories = px.pie(
                    df_categories, values="개수", names="카테고리", title="",
                    color_discrete_sequence=px.colors.qualitative.Set3, hole=0.4,
                )
                fig_categories.update_layout(height=500)
                fig_categories.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_categories, use_container_width=True)

            # 중요도 분포
            st.markdown("**⭐ 키워드 중요도 분포**")
            col_imp1, col_imp2, col_imp3 = st.columns(3)
            total_kw = sum(importance_counts.values())
            with col_imp1:
                high_r = (importance_counts["high"] / total_kw * 100) if total_kw > 0 else 0
                st.metric("High 중요도", f"{importance_counts['high']}개", f"{high_r:.1f}%")
            with col_imp2:
                med_r = (importance_counts["medium"] / total_kw * 100) if total_kw > 0 else 0
                st.metric("Medium 중요도", f"{importance_counts['medium']}개", f"{med_r:.1f}%")
            with col_imp3:
                low_r = (importance_counts["low"] / total_kw * 100) if total_kw > 0 else 0
                st.metric("Low 중요도", f"{importance_counts['low']}개", f"{low_r:.1f}%")

            st.markdown("---")
            st.markdown("**🏷️ 키워드 태그 (중요도별)**")

            high_keywords = [kw["term"] for kw in all_keywords if kw["importance"] == "high"]
            medium_keywords = [kw["term"] for kw in all_keywords if kw["importance"] == "medium"]

            if high_keywords:
                st.markdown("**🔴 High 중요도**")
                high_freq = Counter(high_keywords).most_common(15)
                tags_html = " ".join([
                    f'<span style="display:inline-block;background:linear-gradient(135deg,#ef4444 0%,#991b1b 100%);'
                    f'color:white;padding:6px 14px;margin:4px;border-radius:20px;font-size:13px;font-weight:600;'
                    f'box-shadow:0 2px 4px rgba(239,68,68,0.2);word-wrap:break-word;overflow:hidden;max-width:200px;">'
                    f'🔥 {term[:15] + "…" if len(term) > 15 else term} '
                    f'<span style="opacity:0.8;font-weight:400;margin-left:4px;">{count}</span></span>'
                    for term, count in high_freq
                ])
                st.markdown(tags_html, unsafe_allow_html=True)

            if medium_keywords:
                st.markdown("**🟡 Medium 중요도**")
                medium_freq = Counter(medium_keywords).most_common(15)
                tags_html = " ".join([
                    f'<span style="display:inline-block;background:linear-gradient(135deg,#f59e0b 0%,#b45309 100%);'
                    f'color:white;padding:6px 14px;margin:4px;border-radius:20px;font-size:13px;font-weight:600;'
                    f'box-shadow:0 2px 4px rgba(245,158,11,0.2);word-wrap:break-word;overflow:hidden;max-width:200px;">'
                    f'✨ {term[:15] + "…" if len(term) > 15 else term} '
                    f'<span style="opacity:0.8;font-weight:400;margin-left:4px;">{count}</span></span>'
                    for term, count in medium_freq
                ])
                st.markdown(tags_html, unsafe_allow_html=True)

            with st.expander("📋 전체 키워드 목록 (복사용)"):
                keyword_list = ", ".join([kw for kw, _ in top_keywords])
                st.text_area(
                    "키워드 목록 (Ctrl+A → Ctrl+C로 복사)",
                    value=keyword_list,
                    height=100,
                    key=f"{key_prefix}_kw_copy",
                )

            # ── 🗺️ 인텔리전스 매트릭스 ────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 🧭 인텔리전스 매트릭스 (심층 엔티티 分析)")

            if all_companies or all_technologies or all_countries:
                em_col1, em_col2, em_col3 = st.columns(3)

                with em_col1:
                    st.markdown("**🏢 핫 모멘텀 기업 Top 5**")
                    if all_companies:
                        comp_df = pd.DataFrame(
                            Counter(all_companies).most_common(5),
                            columns=["기업 (Company)", "등장 빈도"],
                        )
                        st.dataframe(comp_df, hide_index=True, use_container_width=True)
                    else:
                        st.info("데이터 없음")

                with em_col2:
                    st.markdown("**🛠️ 부상하는 핵심기술 Top 5**")
                    if all_technologies:
                        tech_df = pd.DataFrame(
                            Counter(all_technologies).most_common(5),
                            columns=["기술 (Tech/Standard)", "등장 빈도"],
                        )
                        st.dataframe(tech_df, hide_index=True, use_container_width=True)
                    else:
                        st.info("데이터 없음")

                with em_col3:
                    st.markdown("**🌍 정책/규제 활성 국가 Top 5**")
                    if all_countries:
                        country_df = pd.DataFrame(
                            Counter(all_countries).most_common(5),
                            columns=["국가 (Country)", "등장 빈도"],
                        )
                        st.dataframe(country_df, hide_index=True, use_container_width=True)
                    else:
                        st.info("데이터 없음")

                # KG 탭
                try:
                    from knowledge_graph import (
                        build_entity_graph, render_graph_html,
                        get_co_occurrence_matrix, detect_surge_entities, get_graph_stats,
                    )
                    _KG_AVAILABLE = True
                except ImportError:
                    _KG_AVAILABLE = False

                if _KG_AVAILABLE:
                    st.markdown("---")
                    _kg_tab1, _kg_tab2, _kg_tab3, _kg_tab4 = st.tabs([
                        "🔥 급등 알림", "🔲 공출현 히트맵", "🕸️ 지식 그래프", "📊 주간 키워드 비교",
                    ])

                    # ── 탭 1: 급등 알림 ────────────────────────────────────────
                    with _kg_tab1:
                        _prev_days = keyword_days * 2
                        _news_prev_raw = load_news_from_db(days=_prev_days, is_analyzed=True)
                        _news_prev = [n for n in _news_prev_raw if n.get("extracted_keywords")]
                        _cutoff = _dt.datetime.now() - _dt.timedelta(days=keyword_days)
                        _news_prev_only = [
                            n for n in _news_prev
                            if n.get("collected_at") and str(n["collected_at"]) < str(_cutoff)
                        ]
                        _surges = detect_surge_entities(
                            news_current=news_with_keywords,
                            news_prev=_news_prev_only,
                            tech_synonyms=TECH_SYNONYMS,
                            threshold=0.5,
                            min_current=2,
                        )
                        if _surges:
                            _type_icon = {"company": "🏢", "tech": "🛠️", "country": "🌍"}
                            for s in _surges[:8]:
                                _icon = _type_icon.get(s["node_type"], "📌")
                                _pct = s["pct_change"]
                                _pct_str = f"+{_pct*100:.0f}%" if _pct != float("inf") else "신규 등장"
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
                            st.info("이전 기간 대비 급등한 엔티티가 없습니다. 分析된 기사가 충분히 누적되면 표시됩니다.")

                    # ── 탭 2: 공출현 히트맵 ────────────────────────────────────
                    with _kg_tab2:
                        _heatmap_n = st.slider(
                            "표시할 상위 N개 (기업·기술 각각)",
                            min_value=3, max_value=12, value=7, step=1,
                            key=f"{key_prefix}_heatmap_n",
                        )
                        _co_matrix = get_co_occurrence_matrix(
                            news_with_keywords, tech_synonyms=TECH_SYNONYMS,
                            top_companies=_heatmap_n, top_techs=_heatmap_n,
                        )
                        if not _co_matrix.empty and _co_matrix.values.sum() > 0:
                            _fig_heat = px.imshow(
                                _co_matrix,
                                labels=dict(x="기술 (Technology)", y="기업 (Company)", color="공출현 횟수"),
                                color_continuous_scale="Blues", aspect="auto", text_auto=True,
                            )
                            _fig_heat.update_layout(
                                height=420,
                                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                font_color="#e8e8e8", coloraxis_showscale=True,
                                margin=dict(l=20, r=20, t=20, b=20),
                            )
                            _fig_heat.update_xaxes(tickangle=-30)
                            st.plotly_chart(_fig_heat, use_container_width=True)
                            st.caption("셀 값 = 같은 기사에 함께 등장한 횟수. 색이 진할수록 연관성이 강합니다.")
                        else:
                            st.info("공출현 데이터가 부족합니다. 기업·기술이 함께 등장하는 기사가 더 필요합니다.")

                    # ── 탭 3: 지식 그래프 ──────────────────────────────────────
                    with _kg_tab3:
                        _graph_col1, _graph_col2 = st.columns([3, 1])
                        with _graph_col2:
                            _min_w = st.slider(
                                "최소 공출현 횟수",
                                min_value=1, max_value=5, value=1, step=1,
                                key=f"{key_prefix}_kg_min_w",
                                help="이 값 이상 함께 등장한 엔티티 쌍만 연결선으로 표시합니다.",
                            )
                            st.markdown(
                                "<div style='margin-top:12px'><b>범례</b><br>"
                                "<span style='color:#4a90e2'>●</span> 🏢 기업<br>"
                                "<span style='color:#e74c3c'>◆</span> 🛠️ 기술<br>"
                                "<span style='color:#2ecc71'>■</span> 🌍 국가<br>"
                                "<small style='color:#888'>노드 크기 = 등장 빈도<br>선 굵기 = 공출현 횟수</small></div>",
                                unsafe_allow_html=True,
                            )
                        with _graph_col1:
                            _G = build_entity_graph(
                                news_with_keywords, tech_synonyms=TECH_SYNONYMS, min_weight=_min_w
                            )
                            _stats = get_graph_stats(_G)
                            if _stats:
                                _s1, _s2, _s3 = st.columns(3)
                                _s1.metric("노드 수", _stats["total_nodes"])
                                _s2.metric("연결 수", _stats["total_edges"])
                                _s3.metric("밀도", f"{_stats['density']:.3f}")
                            _graph_html = render_graph_html(_G, height=520)
                            import streamlit.components.v1 as _components
                            _components.html(_graph_html, height=540, scrolling=False)
                            if _stats and _stats.get("top_central"):
                                with st.expander("📌 중심성 높은 엔티티 Top 5"):
                                    for _name, _score in _stats["top_central"]:
                                        _ntype = (
                                            _G.nodes[_name].get("node_type", "")
                                            if _G and _name in _G.nodes else ""
                                        )
                                        _nicon = {"company": "🏢", "tech": "🛠️", "country": "🌍"}.get(_ntype, "📌")
                                        st.write(f"{_nicon} **{_name}** — 중심성 {_score:.3f}")

                    # ── 탭 4: 주간 키워드 비교 히트맵 ──────────────────────────
                    with _kg_tab4:
                        _wk_prev_raw = load_news_from_db(days=keyword_days * 2)
                        _wk_prev_all = [n for n in _wk_prev_raw if n.get("extracted_keywords")]
                        _wk_cutoff = _dt.datetime.now() - _dt.timedelta(days=keyword_days)
                        _wk_prev_only = [
                            n for n in _wk_prev_all
                            if n.get("collected_at") and str(n["collected_at"]) < str(_wk_cutoff)
                        ]
                        _wk_curr_only = [
                            n for n in _wk_prev_all
                            if n.get("collected_at") and str(n["collected_at"]) >= str(_wk_cutoff)
                        ]
                        if _wk_prev_only and _wk_curr_only:
                            _curr_ctr, _prev_ctr = Counter(), Counter()
                            for _news_set, _ctr in [(_wk_curr_only, _curr_ctr), (_wk_prev_only, _prev_ctr)]:
                                for _n in _news_set:
                                    try:
                                        _kd = json.loads(_n.get("extracted_keywords") or "{}")
                                        for _t in _kd.get("key_technologies", []):
                                            _k = str(_t).strip()
                                            if _k:
                                                _ctr[TECH_SYNONYMS.get(_k.lower(), _k)] += 1
                                    except Exception:
                                        pass
                            _all_keys = sorted(set(list(_curr_ctr.keys()) + list(_prev_ctr.keys())))
                            if _all_keys:
                                _hm_df = pd.DataFrame({
                                    "키워드": _all_keys,
                                    f"이번 {keyword_days}일": [_curr_ctr.get(k, 0) for k in _all_keys],
                                    f"이전 {keyword_days}일": [_prev_ctr.get(k, 0) for k in _all_keys],
                                }).set_index("키워드")
                                _fig_wk = px.imshow(
                                    _hm_df, color_continuous_scale="RdYlGn",
                                    aspect="auto", text_auto=True, labels={"color": "등장 횟수"},
                                )
                                _fig_wk.update_layout(height=max(300, len(_all_keys) * 28 + 60))
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
                st.info("ℹ️ 기업, 기술, 국가 엔티티 데이터가 포함된 최근 分析 뉴스가 없습니다.")

        else:
            st.info("AI가 추출한 키워드가 없습니다. 뉴스를 먼저 分析하세요.")

    except Exception as e:
        st.error(f"키워드 分析 중 오류: {str(e)}")
        st.error(traceback.format_exc())

    # ── AI 모델별 품질 대시보드 ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🤖 AI 모델별 分析 품질")
    try:
        from sqlalchemy import func, case
        with get_db_session() as _mq_db:
            _model_rows = (
                _mq_db.query(
                    NewsArticle.ai_model,
                    func.count(NewsArticle.id).label("total"),
                    func.sum(
                        case(
                            (
                                (NewsArticle.extracted_keywords != None)  # noqa: E711
                                & (NewsArticle.extracted_keywords != ""),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("with_kw"),
                )
                .filter(NewsArticle.ai_model != None)  # noqa: E711
                .group_by(NewsArticle.ai_model)
                .all()
            )

        if _model_rows:
            _mq_cols = st.columns(min(len(_model_rows), 4))
            _model_icons = {"openai": "🟢", "claude": "🟠", "gemini": "🔵", "perplexity": "🟣"}
            for _ci, _row in enumerate(_model_rows):
                _icon = _model_icons.get(str(_row.ai_model).lower(), "⚪")
                _total = _row.total or 0
                _with_kw = int(_row.with_kw or 0)
                _ratio = (_with_kw / _total * 100) if _total > 0 else 0
                with _mq_cols[_ci % 4]:
                    st.metric(
                        label=f"{_icon} {str(_row.ai_model).upper()}",
                        value=f"{_ratio:.0f}%",
                        delta=f"키워드 추출 {_with_kw}/{_total}건",
                        delta_color="normal",
                        help=f"extracted_keywords 존재 비율. 전체 {_total}건 중 {_with_kw}건 정상 추출.",
                    )
        else:
            st.info("AI 모델별 分析 데이터가 없습니다.")
    except Exception as _mq_err:
        st.warning(f"모델 품질 집계 오류: {_mq_err}")
