"""엔티티(기업/국가) 쓰기 시점 정규화 테스트 (순수 함수).

analyze_news_with_ai가 AI JSON 응답을 파싱한 뒤 적용하는 표기 통합 로직만 검증한다.
"""
from news_engine import (
    COMPANY_NORMALIZE,
    COUNTRY_NORMALIZE,
    _normalize_entity_list,
    normalize_extracted_entities,
)


def test_normalize_entity_list_maps_known_variants():
    result = _normalize_entity_list(["Samsung", "Samsung Electronics", "삼성전자"], COMPANY_NORMALIZE)
    assert result == ["삼성전자"]


def test_normalize_entity_list_preserves_order_and_unknowns():
    result = _normalize_entity_list(["애플", "Google", "미확인기업"], COMPANY_NORMALIZE)
    assert result == ["애플", "구글", "미확인기업"]


def test_normalize_entity_list_dedupes_after_mapping():
    result = _normalize_entity_list(["NVIDIA", "Nvidia", "엔비디아"], COMPANY_NORMALIZE)
    assert result == ["엔비디아"]


def test_normalize_entity_list_non_list_passthrough():
    assert _normalize_entity_list("Samsung", COMPANY_NORMALIZE) == "Samsung"
    assert _normalize_entity_list(None, COMPANY_NORMALIZE) is None


def test_normalize_extracted_entities_updates_both_fields():
    parsed = {
        "keywords": [{"term": "6G", "category": "기술", "importance": "high"}],
        "related_companies": ["Samsung", "현대차"],
        "key_technologies": ["6G"],
        "target_countries": ["Korea", "USA"],
        "impact_level": "High",
    }
    result = normalize_extracted_entities(parsed)
    assert result["related_companies"] == ["삼성전자", "현대자동차"]
    assert result["target_countries"] == ["한국", "미국"]
    # 정규화 대상이 아닌 필드는 그대로 유지
    assert result["key_technologies"] == ["6G"]
    assert result["impact_level"] == "High"


def test_normalize_extracted_entities_missing_fields_no_crash():
    parsed = {"keywords": []}
    result = normalize_extracted_entities(parsed)
    assert result == {"keywords": []}


def test_normalize_extracted_entities_non_list_fields_untouched():
    parsed = {"related_companies": "삼성전자", "target_countries": None}
    result = normalize_extracted_entities(parsed)
    assert result["related_companies"] == "삼성전자"
    assert result["target_countries"] is None
