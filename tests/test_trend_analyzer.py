"""주간 트렌드 분석 뉴스 샘플링 회귀 테스트 (순수 함수).

배경: analyze_weekly_trends()가 프롬프트에 넣을 뉴스 목록을 articles[:100]으로
단순 truncate했는데, load_news_from_db()가 collected_at DESC(최신순)로 반환하는
탓에 하루 100~180건씩 쌓이는 상황에서 "최근 100건"이 사실상 최근 1~2일치뿐이라
"핵심 이슈"가 최근 뉴스에만 편중되는 회귀가 있었다(2026-08-03 사용자 리포트로 발견).

1차 수정(_stratified_daily_sample, 날짜별 상한)만으로는 상한 밖 기사가 목록에서
아예 빠져 여전히 이슈를 놓칠 수 있다는 지적에 따라, _build_news_summaries가
전체 기사를 제목 단위로는 빠짐없이 나열하고 날짜별 상한 대상만 분석 스니펫을
덧붙이는 방식으로 보완했다.
"""
from trend_analyzer import _build_news_summaries, _stratified_daily_sample


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
