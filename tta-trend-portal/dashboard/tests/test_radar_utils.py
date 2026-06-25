"""radar_utils 신규 집계·정규화·타임라인 순수 함수 테스트.

엔진/캐시 의존 없이 DataFrame을 직접 주입해 검증한다.
실행: cd tta-trend-portal/dashboard && python -m pytest tests/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# dashboard 디렉토리를 import 경로에 추가 (search.py, radar_utils.py 등)
DASHBOARD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD_DIR))

from radar_utils import (  # noqa: E402
    COMPANY_NORMALIZE,
    COUNTRY_NORMALIZE,
    IMPACT_LEVEL_ORDER,
    article_tech_areas,
    cluster_counts,
    company_counts,
    country_counts,
    entity_detail,
    entity_tech_matrix,
    entity_trend,
    issue_timeline,
    parse_impact,
)


def _article(extracted: dict | str | None, published: str = "2026-06-01", **extra) -> dict:
    """테스트용 기사 row dict 생성."""
    row = {
        "title": extra.get("title", "테스트 기사"),
        "published": published,
        "collected_at": published,
        "extracted_keywords": extracted if isinstance(extracted, str) or extracted is None else json.dumps(extracted, ensure_ascii=False),
    }
    row.update({k: v for k, v in extra.items() if k != "title"})
    return row


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ─────────────────────────── parse_impact ───────────────────────────

class TestParseImpact:
    def test_happy_path(self):
        row = pd.Series(_article({
            "impact_level": "Critical",
            "tta_action_item": "ITU 제출 검토",
            "standardization_gap": "국내 표준 부재",
        }))
        out = parse_impact(row)
        assert out["impact_level"] == "Critical"
        assert out["tta_action_item"] == "ITU 제출 검토"
        assert out["standardization_gap"] == "국내 표준 부재"

    def test_missing_keys_return_empty(self):
        row = pd.Series(_article({"keywords": ["5G"]}))  # 리치 필드 없음
        out = parse_impact(row)
        assert out["impact_level"] == ""
        assert out["tta_action_item"] == ""

    def test_null_json(self):
        row = pd.Series(_article(None))
        out = parse_impact(row)
        assert out == {"impact_level": "", "tta_action_item": "", "standardization_gap": ""}

    def test_malformed_json(self):
        row = pd.Series(_article("{not valid json"))
        out = parse_impact(row)
        assert out["impact_level"] == ""


# ─────────────────────────── country_counts ───────────────────────────

class TestCountryCounts:
    def test_empty_df(self):
        result = country_counts(pd.DataFrame())
        assert result.empty
        assert list(result.columns) == ["country", "count"]

    def test_no_country_field(self):
        df = _df([_article({"impact_level": "High"})])
        assert country_counts(df).empty

    def test_basic_aggregation(self):
        df = _df([
            _article({"target_countries": ["한국", "미국"]}),
            _article({"target_countries": ["한국"]}),
        ])
        result = country_counts(df)
        counts = dict(zip(result["country"], result["count"]))
        assert counts["한국"] == 2
        assert counts["미국"] == 1

    def test_normalization_merges_aliases(self):
        # 한국 + 대한민국 → 한국, 미국 + United States → 미국
        df = _df([
            _article({"target_countries": ["한국"]}),
            _article({"target_countries": ["대한민국"]}),
            _article({"target_countries": ["미국"]}),
            _article({"target_countries": ["United States"]}),
        ])
        result = country_counts(df)
        counts = dict(zip(result["country"], result["count"]))
        assert counts["한국"] == 2  # 한국 + 대한민국
        assert counts["미국"] == 2  # 미국 + United States
        assert "대한민국" not in counts
        assert "United States" not in counts

    def test_string_type_target_countries(self):
        # keyword_items 내부 가드: str 타입도 처리되어야 함
        df = _df([_article({"target_countries": "한국"})])
        result = country_counts(df)
        assert dict(zip(result["country"], result["count"]))["한국"] == 1

    def test_counts_articles_not_mentions(self):
        # keyword_items()가 기사 내 중복을 제거 → "언급 기사 수" 의미.
        # 한 기사에 한국이 3번 나와도 1로 카운트된다 (기존 레이더와 일관).
        df = _df([_article({"target_countries": ["한국", "한국", "한국"]})])
        result = country_counts(df)
        assert dict(zip(result["country"], result["count"]))["한국"] == 1

    def test_sorted_descending(self):
        df = _df([
            _article({"target_countries": ["한국"]}),
            _article({"target_countries": ["한국"]}),
            _article({"target_countries": ["미국"]}),
        ])
        result = country_counts(df)
        assert result.iloc[0]["country"] == "한국"  # 2개 기사 > 미국 1개 기사
        assert result["count"].tolist() == sorted(result["count"].tolist(), reverse=True)


# ─────────────────────────── company_counts ───────────────────────────

class TestCompanyCounts:
    def test_empty_df(self):
        result = company_counts(pd.DataFrame())
        assert result.empty
        assert list(result.columns) == ["company", "count"]

    def test_normalization_nvidia_variants(self):
        # 엔비디아 분산 통합 — 외부 의견이 지적한 핵심 케이스
        df = _df([
            _article({"related_companies": ["엔비디아"]}),
            _article({"related_companies": ["NVIDIA"]}),
            _article({"related_companies": ["Nvidia"]}),
        ])
        result = company_counts(df)
        counts = dict(zip(result["company"], result["count"]))
        assert counts["엔비디아"] == 3
        assert "NVIDIA" not in counts
        assert "Nvidia" not in counts

    def test_hyundai_group_merge(self):
        df = _df([
            _article({"related_companies": ["현대차"]}),
            _article({"related_companies": ["현대자동차"]}),
            _article({"related_companies": ["현대차그룹"]}),
        ])
        result = company_counts(df)
        assert dict(zip(result["company"], result["count"]))["현대자동차"] == 3

    def test_top_n_limit(self):
        df = _df([
            _article({"related_companies": ["A", "B", "C", "D", "E"]}),
        ])
        result = company_counts(df, top_n=3)
        assert len(result) == 3


# ─────────────────────────── issue_timeline ───────────────────────────

class TestIssueTimeline:
    def test_empty_df(self):
        result = issue_timeline(pd.DataFrame())
        assert result.empty
        assert list(result.columns) == ["technology", "week", "count", "stage"]

    def test_no_tech_field(self):
        df = _df([_article({"target_countries": ["한국"]})])
        assert issue_timeline(df).empty

    def test_article_without_date_skipped(self):
        df = _df([{
            "title": "no date",
            "published": None,
            "collected_at": None,
            "extracted_keywords": json.dumps({"key_technologies": ["6G"]}),
        }])
        assert issue_timeline(df).empty

    def test_weekly_bucketing(self):
        df = _df([
            _article({"key_technologies": ["6G"]}, published="2026-06-01"),
            _article({"key_technologies": ["6G"]}, published="2026-06-02"),  # 같은 주
            _article({"key_technologies": ["6G"]}, published="2026-06-15"),  # 다른 주
        ])
        result = issue_timeline(df)
        sixg = result[result["technology"] == "6G"]
        assert len(sixg) == 2  # 2개 주차
        assert sixg["count"].sum() == 3

    def test_surge_stage(self):
        # 최근 주차가 평균의 1.5배 초과 → 급등
        rows = []
        for wk in ["2026-05-04", "2026-05-11", "2026-05-18"]:
            rows.append(_article({"key_technologies": ["로봇"]}, published=wk))
        # 최신 주차에 폭증
        for _ in range(10):
            rows.append(_article({"key_technologies": ["로봇"]}, published="2026-06-01"))
        result = issue_timeline(_df(rows))
        latest_stage = result[result["technology"] == "로봇"].sort_values("week").iloc[-1]["stage"]
        assert latest_stage == "급등"

    def test_max_tech_per_article(self):
        # 기사당 상위 N개 기술만 (노이즈 제어)
        df = _df([_article({"key_technologies": ["A", "B", "C", "D", "E"]}, published="2026-06-01")])
        result = issue_timeline(df, top_n=10, max_tech_per_article=2)
        assert result["count"].sum() == 2


# ─────────────────────────── cluster_counts ───────────────────────────

class TestClusterCounts:
    def test_empty_df(self):
        result = cluster_counts(pd.DataFrame())
        assert result.empty
        assert list(result.columns) == ["cluster", "count"]

    def test_missing_column(self):
        df = pd.DataFrame([{"title": "a"}])  # cluster_label 컬럼 없음
        assert cluster_counts(df).empty

    def test_all_null_labels(self):
        df = pd.DataFrame([{"cluster_label": None}, {"cluster_label": ""}])
        assert cluster_counts(df).empty

    def test_basic_distribution(self):
        df = pd.DataFrame([
            {"cluster_label": "6G · IMT-2030"},
            {"cluster_label": "6G · IMT-2030"},
            {"cluster_label": "위성통신 · 스타링크"},
            {"cluster_label": None},  # 무시
        ])
        result = cluster_counts(df)
        counts = dict(zip(result["cluster"], result["count"]))
        assert counts["6G · IMT-2030"] == 2
        assert counts["위성통신 · 스타링크"] == 1
        assert result.iloc[0]["cluster"] == "6G · IMT-2030"  # 내림차순

    def test_top_n(self):
        df = pd.DataFrame([{"cluster_label": f"c{i}"} for i in range(5)])
        assert len(cluster_counts(df, top_n=3)) == 3


# ─────────────────────────── 기술영역 매트릭스 ───────────────────────────

class TestTechAreas:
    def test_article_tech_areas_synonyms(self):
        # 6G·IMT-2030 → 6G, 보안 → 사이버보안, SDV → 자율주행
        row = pd.Series(_article({"key_technologies": ["IMT-2030", "보안", "SDV"]}))
        areas = article_tech_areas(row)
        assert "6G" in areas
        assert "사이버보안" in areas
        assert "자율주행" in areas

    def test_article_tech_areas_dict_format(self):
        row = pd.Series(_article({"key_technologies": [{"term": "6G", "category": "기술"}]}))
        assert "6G" in article_tech_areas(row)

    def test_article_tech_areas_empty(self):
        row = pd.Series(_article({"target_countries": ["한국"]}))
        assert article_tech_areas(row) == set()


class TestEntityTechMatrix:
    def test_empty(self):
        assert entity_tech_matrix(pd.DataFrame(), "국가", COUNTRY_NORMALIZE).empty

    def test_country_tech_crosstab(self):
        df = _df([
            _article({"target_countries": ["한국"], "key_technologies": ["6G", "AI"]}),
            _article({"target_countries": ["한국"], "key_technologies": ["AI"]}),
            _article({"target_countries": ["미국"], "key_technologies": ["위성"]}),
        ])
        m = entity_tech_matrix(df, "국가", COUNTRY_NORMALIZE)
        assert m.loc["한국", "AI"] == 2
        assert m.loc["한국", "6G"] == 1
        assert m.loc["미국", "위성통신"] == 1

    def test_top_entities_limit(self):
        df = _df([
            _article({"target_countries": [c], "key_technologies": ["AI"]})
            for c in ["한국", "미국", "중국", "일본", "영국"]
        ])
        m = entity_tech_matrix(df, "국가", COUNTRY_NORMALIZE, top_entities=2)
        assert len(m) == 2


class TestEntityDetail:
    def test_basic(self):
        df = _df([
            _article({"target_countries": ["미국"], "key_technologies": ["AI"], "related_companies": ["엔비디아"]},
                     title="미국 AI"),
            _article({"target_countries": ["미국"], "key_technologies": ["위성"]}, title="미국 위성"),
        ])
        d = entity_detail(df, "국가", "미국", COUNTRY_NORMALIZE)
        assert d["article_count"] == 2
        assert "AI" in d["top_areas"]
        assert "엔비디아" in d["top_companies"]

    def test_no_match(self):
        df = _df([_article({"target_countries": ["한국"]})])
        d = entity_detail(df, "국가", "미국", COUNTRY_NORMALIZE)
        assert d["article_count"] == 0
        assert d["top_areas"] == []


class TestEntityTrend:
    def test_growth(self):
        recent = _df([_article({"related_companies": ["엔비디아"]}) for _ in range(3)])
        baseline = _df([_article({"related_companies": ["엔비디아"]})])
        tr = entity_trend(recent, baseline, "기업", COMPANY_NORMALIZE)
        row = tr[tr["name"] == "엔비디아"].iloc[0]
        assert row["recent"] == 3
        assert row["baseline"] == 1
        assert row["growth"] == 2

    def test_empty_recent(self):
        tr = entity_trend(pd.DataFrame(), pd.DataFrame(), "기업", COMPANY_NORMALIZE)
        assert tr.empty


# ─────────────────────────── 상수 무결성 ───────────────────────────

class TestConstants:
    def test_impact_order_complete(self):
        assert IMPACT_LEVEL_ORDER["Critical"] > IMPACT_LEVEL_ORDER["High"]
        assert IMPACT_LEVEL_ORDER["High"] > IMPACT_LEVEL_ORDER["Medium"]
        assert IMPACT_LEVEL_ORDER["Medium"] > IMPACT_LEVEL_ORDER["Low"]
        assert IMPACT_LEVEL_ORDER[""] == 0

    def test_normalize_dicts_are_str_to_str(self):
        for d in (COUNTRY_NORMALIZE, COMPANY_NORMALIZE):
            for k, v in d.items():
                assert isinstance(k, str) and isinstance(v, str)
                assert v not in d, f"{v}는 정규화 대상이 아니라 표준형이어야 함 (체인 매핑 금지)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
