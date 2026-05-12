"""
IRONAGE AI Analytics System v5.0
지식 그래프 (Knowledge Graph) 모듈

기능:
- 뉴스 기사 엔티티(기업·기술·국가) 간 공출현(co-occurrence) 그래프 빌드 (NetworkX)
- Pyvis HTML 인터랙티브 시각화 → Streamlit 임베드
- 기업 × 기술 공출현 매트릭스 (Plotly 히트맵용 DataFrame)
- 급등 엔티티 자동 감지 (이전 기간 대비 증가율)
"""

import json
import os
import tempfile
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False

try:
    from pyvis.network import Network
    PYVIS_AVAILABLE = True
except ImportError:
    PYVIS_AVAILABLE = False


# 노드 유형별 시각 스타일
_NODE_STYLES: Dict[str, Dict] = {
    'company': {'color': '#4a90e2', 'base_size': 20, 'shape': 'dot',     'prefix': '🏢'},
    'tech':    {'color': '#e74c3c', 'base_size': 18, 'shape': 'diamond', 'prefix': '🛠️'},
    'country': {'color': '#2ecc71', 'base_size': 16, 'shape': 'square',  'prefix': '🌍'},
}

_PYVIS_OPTIONS = """{
  "physics": {
    "enabled": true,
    "barnesHut": {
      "gravitationalConstant": -8000,
      "centralGravity": 0.3,
      "springConstant": 0.04,
      "damping": 0.09
    }
  },
  "nodes": { "borderWidth": 2, "shadow": true },
  "edges": { "smooth": {"type": "continuous"}, "shadow": true },
  "interaction": { "hover": true, "tooltipDelay": 200, "navigationButtons": true }
}"""


def _parse_entities(
    article: Dict,
    tech_synonyms: Optional[Dict] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """기사 1건에서 기업·기술·국가 리스트 반환."""
    tech_synonyms = tech_synonyms or {}
    raw = article.get('extracted_keywords')
    if not raw:
        return [], [], []
    try:
        kd = json.loads(raw)
    except Exception:
        return [], [], []

    companies = [c.strip() for c in kd.get('related_companies', []) if c and c.strip()]
    techs_raw = [t.strip() for t in kd.get('key_technologies', []) if t and t.strip()]
    techs = [tech_synonyms.get(t.lower(), t) for t in techs_raw]
    countries = [c.strip() for c in kd.get('target_countries', []) if c and c.strip()]
    return companies, techs, countries


# ==============================================================================
# --- 그래프 빌드 ---
# ==============================================================================

def build_entity_graph(
    news_list: List[Dict],
    tech_synonyms: Optional[Dict] = None,
    min_weight: int = 1,
) -> "nx.Graph":
    """
    뉴스 기사 리스트에서 엔티티 공출현 그래프 빌드.

    Returns networkx.Graph (NX_AVAILABLE=False 이면 None)
    """
    if not NX_AVAILABLE:
        return None

    G = nx.Graph()

    for article in news_list:
        companies, techs, countries = _parse_entities(article, tech_synonyms)

        all_entities = (
            [(c, 'company') for c in companies] +
            [(t, 'tech')    for t in techs] +
            [(co, 'country') for co in countries]
        )

        for name, ntype in all_entities:
            if not G.has_node(name):
                G.add_node(name, node_type=ntype, count=0)
            G.nodes[name]['count'] += 1

        # 같은 기사에 등장한 엔티티 쌍 → 엣지 가중치 +1
        seen_pairs = set()
        for i in range(len(all_entities)):
            for j in range(i + 1, len(all_entities)):
                a, _ = all_entities[i]
                b, _ = all_entities[j]
                if a == b:
                    continue
                pair = (min(a, b), max(a, b))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if G.has_edge(a, b):
                    G[a][b]['weight'] += 1
                else:
                    G.add_edge(a, b, weight=1)

    # 최소 공출현 횟수 미달 엣지 제거 후 고립 노드 제거
    weak = [(u, v) for u, v, d in G.edges(data=True) if d['weight'] < min_weight]
    G.remove_edges_from(weak)
    G.remove_nodes_from(list(nx.isolates(G)))

    return G


# ==============================================================================
# --- Pyvis HTML 렌더링 ---
# ==============================================================================

def render_graph_html(G: "nx.Graph", height: int = 580) -> str:
    """NetworkX 그래프 → Pyvis HTML 문자열 (Streamlit st.components.v1.html 용)."""
    if not NX_AVAILABLE or G is None:
        return "<p style='color:#aaa;text-align:center;'>networkx 라이브러리가 필요합니다: pip install networkx</p>"
    if not PYVIS_AVAILABLE:
        return "<p style='color:#aaa;text-align:center;'>pyvis 라이브러리가 필요합니다: pip install pyvis</p>"
    if len(G.nodes) == 0:
        return "<p style='color:#aaa;text-align:center;padding:40px;'>공출현 데이터가 부족합니다. 더 많은 기사를 분석하세요.</p>"

    net = Network(
        height=f'{height}px',
        width='100%',
        bgcolor='#0f1117',
        font_color='#e8e8e8',
        directed=False,
    )
    net.set_options(_PYVIS_OPTIONS)

    for node, data in G.nodes(data=True):
        ntype = data.get('node_type', 'company')
        style = _NODE_STYLES.get(ntype, _NODE_STYLES['company'])
        count = data.get('count', 1)
        size = style['base_size'] + min(count * 3, 24)

        net.add_node(
            node,
            label=f"{style['prefix']} {node}",
            color=style['color'],
            size=size,
            shape=style['shape'],
            title=f"<b>{node}</b><br>유형: {ntype}<br>등장: {count}회",
        )

    for u, v, data in G.edges(data=True):
        weight = data.get('weight', 1)
        net.add_edge(
            u, v,
            value=weight,
            width=max(1, min(weight * 0.8, 6)),
            title=f"공출현: {weight}회",
        )

    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.html')
    os.close(tmp_fd)
    try:
        net.save_graph(tmp_path)
        with open(tmp_path, 'r', encoding='utf-8') as f:
            html = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return html


# ==============================================================================
# --- 공출현 매트릭스 ---
# ==============================================================================

def get_co_occurrence_matrix(
    news_list: List[Dict],
    tech_synonyms: Optional[Dict] = None,
    top_companies: int = 8,
    top_techs: int = 8,
) -> pd.DataFrame:
    """
    기업 × 기술 공출현 카운트 DataFrame 반환.
    행=기업, 열=기술, 값=같은 기사에 함께 등장한 횟수.
    """
    tech_synonyms = tech_synonyms or {}
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    company_counts: Dict[str, int] = defaultdict(int)
    tech_counts: Dict[str, int] = defaultdict(int)

    for article in news_list:
        companies, techs, _ = _parse_entities(article, tech_synonyms)
        for c in companies:
            company_counts[c] += 1
        for t in techs:
            tech_counts[t] += 1
        for c in companies:
            for t in techs:
                matrix[c][t] += 1

    top_c = [c for c, _ in sorted(company_counts.items(), key=lambda x: -x[1])[:top_companies]]
    top_t = [t for t, _ in sorted(tech_counts.items(), key=lambda x: -x[1])[:top_techs]]

    if not top_c or not top_t:
        return pd.DataFrame()

    rows = [{t: matrix[c].get(t, 0) for t in top_t} for c in top_c]
    return pd.DataFrame(rows, index=top_c, columns=top_t)


# ==============================================================================
# --- 급등 엔티티 감지 ---
# ==============================================================================

def detect_surge_entities(
    news_current: List[Dict],
    news_prev: List[Dict],
    tech_synonyms: Optional[Dict] = None,
    threshold: float = 0.5,
    min_current: int = 2,
) -> List[Dict]:
    """
    전 기간 대비 등장 횟수가 threshold 이상 급증한 엔티티 목록 반환.

    Returns list of {name, node_type, prev_count, curr_count, pct_change}
    """
    tech_synonyms = tech_synonyms or {}

    def count_entities(news_list):
        counts: Dict[str, Dict] = {}
        for article in news_list:
            companies, techs, countries = _parse_entities(article, tech_synonyms)
            for name, ntype in (
                [(c, 'company') for c in companies] +
                [(t, 'tech')    for t in techs] +
                [(co, 'country') for co in countries]
            ):
                if name not in counts:
                    counts[name] = {'node_type': ntype, 'count': 0}
                counts[name]['count'] += 1
        return counts

    curr_counts = count_entities(news_current)
    prev_counts = count_entities(news_prev)

    surges = []
    for name, info in curr_counts.items():
        curr = info['count']
        if curr < min_current:
            continue
        prev = prev_counts.get(name, {}).get('count', 0)
        if prev == 0:
            pct = float('inf')
        else:
            pct = (curr - prev) / prev

        if pct >= threshold:
            surges.append({
                'name': name,
                'node_type': info['node_type'],
                'prev_count': prev,
                'curr_count': curr,
                'pct_change': pct,
            })

    return sorted(surges, key=lambda x: -x['pct_change'])


# ==============================================================================
# --- 그래프 통계 ---
# ==============================================================================

def get_graph_stats(G: "nx.Graph") -> Dict:
    """그래프 기본 통계 반환."""
    if not NX_AVAILABLE or G is None or len(G.nodes) == 0:
        return {}

    node_types = {}
    for _, data in G.nodes(data=True):
        ntype = data.get('node_type', 'unknown')
        node_types[ntype] = node_types.get(ntype, 0) + 1

    centrality = nx.degree_centrality(G)
    top_central = sorted(centrality.items(), key=lambda x: -x[1])[:5]

    return {
        'total_nodes': G.number_of_nodes(),
        'total_edges': G.number_of_edges(),
        'node_types': node_types,
        'top_central': top_central,
        'density': nx.density(G),
    }
