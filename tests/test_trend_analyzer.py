"""주간 트렌드 분석 뉴스 샘플링 회귀 테스트 (순수 함수).

배경: analyze_weekly_trends()가 프롬프트에 넣을 뉴스 목록을 articles[:100]으로
단순 truncate했는데, load_news_from_db()가 collected_at DESC(최신순)로 반환하는
탓에 하루 100~180건씩 쌓이는 상황에서 "최근 100건"이 사실상 최근 1~2일치뿐이라
"핵심 이슈"가 최근 뉴스에만 편중되는 회귀가 있었다(2026-08-03 사용자 리포트로 발견).

1차 수정(_stratified_daily_sample, 날짜별 상한)만으로는 상한 밖 기사가 목록에서
아예 빠져 여전히 이슈를 놓칠 수 있다는 지적에 따라, _build_news_summaries가
전체 기사를 제목 단위로는 빠짐없이 나열하고 날짜별 상한 대상만 분석 스니펫을
덧붙이는 방식으로 보완했다.

2차 수정(_unit_balanced_enriched_ids): 날짜별 상한만으로는 단(unit) 편중을
막지 못한다 — 뉴스 절대량이 큰 단(AI융합표준단)이 날짜별 상한 안에서도 표본을
독점해, 위성통신·6G처럼 특정 단(전파네트워크표준단)에 집중된 주제가 실제로는
매일 보도됐음에도 주간 핵심 이슈에서 통째로 빠지는 회귀가 있었다(2026-08-10
사용자 리포트로 발견).
"""
import trend_analyzer
from trend_analyzer import (
    _build_news_summaries,
    _stratified_daily_sample,
    _unit_balanced_enriched_ids,
)


def _article(day: str, idx: int, **extra) -> dict:
    row = {
        'title': f'{day}-{idx}',
        'collected_at': f'{day} {23 - idx:02d}:00',  # 같은 날 안에서도 최신 우선 순서 유지 확인용
    }
    row.update(extra)
    return row


def _make_recency_sorted(days_counts: dict) -> list:
    """날짜별 건수를 받아 collected_at 내림차순(최신 날짜 먼저)으로 정렬된 기사 리스트 생성."""
    articles = []
    for day in sorted(days_counts.keys(), reverse=True):
        for i in range(days_counts[day]):
            articles.append(_article(day, i))
    return articles


class TestStratifiedDailySample:
    def test_skewed_recent_days_still_covers_all_days(self):
        # 실측과 유사한 분포: 최근 이틀에 절반 이상 몰려 있음
        counts = {
            '2026-07-27': 162, '2026-07-28': 180, '2026-07-29': 146,
            '2026-07-30': 142, '2026-07-31': 103, '2026-08-01': 108,
            '2026-08-02': 125,
        }
        articles = _make_recency_sorted(counts)
        sampled = _stratified_daily_sample(articles, per_day_limit=30)

        sampled_days = {a['collected_at'][:10] for a in sampled}
        assert sampled_days == set(counts.keys())  # 7일 전부 대표됨

    def test_per_day_cap_enforced(self):
        counts = {'2026-08-01': 50, '2026-08-02': 200}
        articles = _make_recency_sorted(counts)
        sampled = _stratified_daily_sample(articles, per_day_limit=30)

        from collections import Counter
        day_counts = Counter(a['collected_at'][:10] for a in sampled)
        assert day_counts['2026-08-01'] == 30
        assert day_counts['2026-08-02'] == 30
        assert len(sampled) == 60

    def test_days_under_limit_kept_entirely(self):
        counts = {'2026-08-01': 5, '2026-08-02': 12}
        articles = _make_recency_sorted(counts)
        sampled = _stratified_daily_sample(articles, per_day_limit=30)
        assert len(sampled) == 17

    def test_recency_order_preserved_within_day(self):
        articles = _make_recency_sorted({'2026-08-02': 5})
        sampled = _stratified_daily_sample(articles, per_day_limit=3)
        # _article()은 idx가 클수록 collected_at 시각이 더 이르게(과거) 만들어짐 →
        # 앞쪽(idx 0,1,2)이 그날 안에서 더 최신이어야 함
        assert [a['title'] for a in sampled] == ['2026-08-02-0', '2026-08-02-1', '2026-08-02-2']

    def test_empty_input(self):
        assert _stratified_daily_sample([], per_day_limit=30) == []

    def test_falls_back_to_published_when_collected_at_missing(self):
        articles = [
            {'title': 'a', 'published': '2026-08-01 10:00'},
            {'title': 'b', 'published': '2026-08-02 10:00'},
        ]
        sampled = _stratified_daily_sample(articles, per_day_limit=30)
        assert len(sampled) == 2


class TestBuildNewsSummaries:
    def test_every_article_appears_even_outside_enrichment_cap(self):
        """날짜별 상한 밖 기사도 제목은 목록에서 빠지지 않아야 한다 — 이번 보완의 핵심."""
        counts = {'2026-08-01': 50, '2026-08-02': 200}
        articles = _make_recency_sorted(counts)
        for a in articles:
            a['analysis_result'] = f"{a['title']} 분석 내용"

        enriched_ids = {id(a) for a in _stratified_daily_sample(articles, per_day_limit=30)}
        summaries = _build_news_summaries(articles, enriched_ids)

        assert len(summaries) == len(articles) == 250
        combined = "\n".join(summaries)
        for a in articles:
            assert a['title'] in combined  # 250건 전부 제목이 등장

    def test_only_enriched_articles_get_analysis_snippet(self):
        articles = _make_recency_sorted({'2026-08-01': 5})
        for a in articles:
            a['analysis_result'] = f"상세분석-{a['title']}"

        enriched_ids = {id(articles[0]), id(articles[1])}
        summaries = _build_news_summaries(articles, enriched_ids)

        assert '분석: 상세분석-2026-08-01-0' in summaries[0]
        assert '분석: 상세분석-2026-08-01-1' in summaries[1]
        for s in summaries[2:]:
            assert '분석:' not in s

    def test_numbering_matches_position_not_enrichment(self):
        articles = _make_recency_sorted({'2026-08-01': 3})
        summaries = _build_news_summaries(articles, enriched=set())
        assert summaries[0].startswith('1. ')
        assert summaries[1].startswith('2. ')
        assert summaries[2].startswith('3. ')

    def test_empty_articles(self):
        assert _build_news_summaries([], enriched=set()) == []


def _unit_article(day: str, idx: int, unit_id) -> dict:
    return {
        'title': f'{day}-{idx}-u{unit_id}',
        'collected_at': f'{day} {23 - idx:02d}:00',
        'unit_id': unit_id,
    }


class TestUnitBalancedEnrichedIds:
    def _mock_units(self, monkeypatch, ids=(1, 2, 3, 4)):
        monkeypatch.setattr(trend_analyzer, 'get_all_units', lambda: [{'id': i} for i in ids])

    def test_minority_unit_survives_dominant_unit_same_day(self, monkeypatch):
        """실제 회귀 재현: 같은 날 안에서 절대량이 큰 단(3)의 기사가 먼저 나열되면
        날짜별 상한(30)만으로는 소수 단(4)의 기사가 통째로 잘려나간다 —
        단별 안배가 이를 막아야 한다."""
        self._mock_units(monkeypatch)
        day = '2026-08-06'
        # 단3(AI) 40건이 그날 앞쪽(더 최신)을 모두 차지, 단4(전파망) 5건은 뒤쪽
        articles = [_unit_article(day, i, unit_id=3) for i in range(40)]
        articles += [_unit_article(day, i, unit_id=4) for i in range(40, 45)]

        day_only = {id(a) for a in _stratified_daily_sample(articles, per_day_limit=30)}
        assert not any(a['unit_id'] == 4 for a in articles if id(a) in day_only), \
            "재현 전제: 날짜별 상한만으로는 단4가 전부 잘려야 함"

        enriched = _unit_balanced_enriched_ids(articles, per_unit=20)
        unit4_enriched = [a for a in articles if a['unit_id'] == 4 and id(a) in enriched]
        assert len(unit4_enriched) == 5  # 단4 전체(5건, 20건 미만이라 전부 확보)

    def test_per_unit_cap_enforced_when_unit_has_more_than_min(self, monkeypatch):
        """fill_per_day_limit=0으로 나머지 채움 단계를 비활성화해 단별 확보
        단계 자체가 정확히 per_unit건에서 멈추는지만 격리해서 확인한다."""
        self._mock_units(monkeypatch, ids=(1, 2))
        articles = [_unit_article('2026-08-06', i, unit_id=1) for i in range(30)]
        articles += [_unit_article('2026-08-06', i, unit_id=2) for i in range(30, 60)]

        enriched = _unit_balanced_enriched_ids(articles, per_unit=20, fill_per_day_limit=0)
        unit1 = [a for a in articles if a['unit_id'] == 1 and id(a) in enriched]
        unit2 = [a for a in articles if a['unit_id'] == 2 and id(a) in enriched]
        assert len(unit1) == 20
        assert len(unit2) == 20
        # 단별 확보분은 그 단 안에서 최신순(가장 이른 idx)이어야 함
        assert {a['title'] for a in unit1} == {f'2026-08-06-{i}-u1' for i in range(20)}

    def test_remaining_slots_filled_by_daily_stratified_sample(self, monkeypatch):
        """단별 확보 후 남는 기사는 날짜별 상한으로 채워져야 한다(날짜 편중 방지 유지)."""
        self._mock_units(monkeypatch, ids=(1,))
        counts = {'2026-08-01': 50, '2026-08-02': 50}
        articles = []
        for day, n in counts.items():
            articles += [_unit_article(day, i, unit_id=1) for i in range(n)]

        enriched = _unit_balanced_enriched_ids(articles, per_unit=10, fill_per_day_limit=15)
        enriched_days = {a['collected_at'][:10] for a in articles if id(a) in enriched}
        assert enriched_days == {'2026-08-01', '2026-08-02'}  # 두 날짜 모두 대표됨

    def test_articles_never_double_counted_between_unit_and_fill_phase(self, monkeypatch):
        self._mock_units(monkeypatch, ids=(1, 2))
        articles = [_unit_article('2026-08-06', i, unit_id=1) for i in range(5)]
        articles += [_unit_article('2026-08-06', i, unit_id=2) for i in range(5, 10)]

        enriched = _unit_balanced_enriched_ids(articles, per_unit=20)
        # 전체 10건뿐이므로 전부 확보되고, 중복 없이 정확히 10개 id만 존재해야 함
        assert len(enriched) == 10

    def test_unassigned_unit_id_only_reachable_via_fill_phase(self, monkeypatch):
        """unit_id가 None(미배정)인 기사는 단별 확보 대상이 아니라 나머지 채움에서만 나온다."""
        self._mock_units(monkeypatch, ids=(1,))
        articles = [_unit_article('2026-08-06', i, unit_id=None) for i in range(5)]
        enriched = _unit_balanced_enriched_ids(articles, per_unit=20)
        assert len(enriched) == 5

    def test_empty_input(self, monkeypatch):
        self._mock_units(monkeypatch)
        assert _unit_balanced_enriched_ids([], per_unit=20) == set()

    def test_end_to_end_all_units_get_analysis_snippet_in_prompt(self, monkeypatch):
        """실제 프롬프트 조립까지: 소수 단 기사도 '분석:' 스니펫이 붙어야 한다."""
        self._mock_units(monkeypatch, ids=(3, 4))
        day = '2026-08-06'
        articles = [_unit_article(day, i, unit_id=3) for i in range(40)]
        articles += [_unit_article(day, i, unit_id=4) for i in range(40, 43)]
        for a in articles:
            a['analysis_result'] = f"상세분석-{a['title']}"

        enriched = _unit_balanced_enriched_ids(articles, per_unit=20)
        summaries = _build_news_summaries(articles, enriched)
        combined = '\n'.join(summaries)
        for a in articles:
            if a['unit_id'] == 4:
                assert f"분석: 상세분석-{a['title']}" in combined
