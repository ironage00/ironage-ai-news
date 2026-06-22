import itertools
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from search import parse_keywords


ENTITY_KEYS = {
    "related_companies": "company",
    "key_technologies": "tech",
    "target_countries": "country",
    "standards_keywords": "standard",
}


def article_entities(row: pd.Series) -> List[Tuple[str, str]]:
    data = parse_keywords(row.get("extracted_keywords"))
    entities: List[Tuple[str, str]] = []
    for key, entity_type in ENTITY_KEYS.items():
        value = data.get(key, [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            continue
        for item in value:
            name = str(item).strip()
            if name:
                entities.append((name, entity_type))
    return list(dict.fromkeys(entities))


def build_edges(df: pd.DataFrame, min_weight: int = 1) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_counts: Counter[Tuple[str, str]] = Counter()
    edge_counts: Counter[Tuple[str, str]] = Counter()
    edge_articles: Dict[Tuple[str, str], set] = defaultdict(set)

    for _, row in df.iterrows():
        entities = article_entities(row)
        for entity in entities:
            node_counts[entity] += 1
        names = sorted({name for name, _ in entities})
        for a, b in itertools.combinations(names, 2):
            key = (a, b)
            edge_counts[key] += 1
            edge_articles[key].add(row.get("id"))

    nodes = [
        {"entity": name, "entity_type": entity_type, "count": count}
        for (name, entity_type), count in node_counts.items()
    ]
    edges = [
        {
            "source": a,
            "target": b,
            "weight": weight,
            "article_count": len(edge_articles[(a, b)]),
        }
        for (a, b), weight in edge_counts.items()
        if weight >= min_weight
    ]
    return pd.DataFrame(nodes), pd.DataFrame(edges)


def graph_summary(nodes: pd.DataFrame, edges: pd.DataFrame, top_n: int = 10) -> str:
    if nodes.empty:
        return "엔티티 데이터가 부족합니다."
    top_nodes = nodes.sort_values("count", ascending=False).head(top_n)
    lines = ["관계망 중심 엔티티:"]
    for _, row in top_nodes.iterrows():
        lines.append(f"- {row['entity']} ({row['entity_type']}): {int(row['count'])}회")
    if not edges.empty:
        lines.append("\n주요 공출현 관계:")
        for _, row in edges.sort_values("weight", ascending=False).head(top_n).iterrows():
            lines.append(f"- {row['source']} ↔ {row['target']}: {int(row['weight'])}회")
    return "\n".join(lines)


def to_plotly_edges(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges
    return edges.sort_values("weight", ascending=False).head(50)

