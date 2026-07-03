#!/usr/bin/env python3
"""
Supabase에 이미 쌓인 비ICT 기사 일회성 청소 스크립트 (Phase C3).

Stage 0 필터(_collect_stage_filter_reason)가 지금 수집 단계에서 걸러내는
기준을, 과거에 저장된 기존 데이터에 소급 적용해 삭제 대상을 찾는다.
차익실현·코스피·스포츠·연예 등 사용자가 보고한 쓰레기 기사를 정리한다.

안전장치:
  - 기본은 dry-run — 삭제하지 않고 건수·샘플만 보여준다.
  - is_selected=True 또는 is_analyzed=True 기사는 대상에서 절대 제외
    (AI 선별/심층분석 결과물이므로 실수로 지우면 복구 불가)
  - --older-than-hours로 최근 수집분(파이프라인 진행 중일 수 있음)도 기본 제외
  - 실제 삭제는 --confirm 플래그를 명시해야 실행됨

사용법:
  python scripts/cleanup_junk_articles.py                # dry-run 리포트만
  python scripts/cleanup_junk_articles.py --confirm       # 실제 삭제
"""
import argparse
import datetime
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news_engine import (  # noqa: E402
    NewsArticle,
    get_db_session,
    _collect_stage_filter_reason,
)

DEFAULT_OLDER_THAN_HOURS = 24  # 최근 24시간 이내 수집분은 파이프라인 진행 중일 수 있어 제외


def find_junk_ids(older_than_hours: int) -> dict:
    """삭제 후보 조회. {id: (reason, title)} 반환.

    is_selected/is_analyzed는 명시적으로 False인 행만 후보로 삼는다
    (SQLAlchemy `.is_(False)` → SQL `= false`). NULL 값 행은 3치 논리상
    `NULL = false`가 NULL이 되어 WHERE 조건을 만족하지 않으므로 후보에서
    자동 제외된다 — 즉 True/NULL 둘 다 "보호 대상"으로 취급되며, 이는
    "정체가 확실하지 않으면 지우지 않는다"는 안전 방향과 일치한다.
    (`isnot(True)`로 바꾸면 NULL 행이 후보에 포함되어 오히려 위험해지므로 사용 금지.)
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=older_than_hours)

    with get_db_session() as session:
        rows = (
            session.query(NewsArticle.id, NewsArticle.title, NewsArticle.content)
            .filter(
                NewsArticle.is_selected.is_(False),   # AI 선별 결과물(및 NULL) 보호
                NewsArticle.is_analyzed.is_(False),    # 심층분석 결과물(및 NULL) 보호
                NewsArticle.collected_at < cutoff.replace(tzinfo=None),
            )
            .all()
        )

    junk: dict = {}
    for row in rows:
        reason = _collect_stage_filter_reason({
            'title': row.title or '',
            'summary': (row.content or '')[:300],
        })
        if reason:
            junk[row.id] = (reason, row.title or '')
    return junk


def report(junk: dict) -> None:
    reasons: Counter = Counter(r for r, _ in junk.values())
    print(f"\n삭제 후보: {len(junk)}건\n")
    print(f"{'사유':<24} {'건수':>6}")
    print("-" * 32)
    for reason, count in reasons.most_common():
        print(f"{reason:<24} {count:>6}")
    print()
    print("샘플 (사유별 최대 3개):")
    shown: Counter = Counter()
    for aid, (reason, title) in junk.items():
        if shown[reason] >= 3:
            continue
        shown[reason] += 1
        print(f"  [{reason}] {title[:60]}")


_BATCH_SIZE = 500


def _batches(ids: list, size: int = _BATCH_SIZE):
    """순수 함수 — id 목록을 size 단위로 쪼갠다 (테스트 가능하도록 delete_junk에서 분리)."""
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def delete_junk(junk: dict) -> int:
    """배치별로 삭제 + 커밋 — 한 배치 실패가 전체 트랜잭션을 롤백하지 않도록,
    또한 대량 삭제 시 잠금 시간을 배치 단위로 제한하기 위해 배치마다 commit()한다."""
    ids = list(junk.keys())
    deleted = 0
    with get_db_session() as session:
        for batch in _batches(ids):
            deleted += (
                session.query(NewsArticle)
                .filter(NewsArticle.id.in_(batch))
                .delete(synchronize_session=False)
            )
            session.commit()  # 배치마다 커밋 — 트랜잭션 크기를 배치 단위로 제한
    return deleted


def main(argv=None):
    parser = argparse.ArgumentParser(description='기존 비ICT 기사 일회성 청소')
    parser.add_argument('--confirm', action='store_true',
                        help='실제 삭제 실행 (기본은 dry-run 리포트만)')
    parser.add_argument('--older-than-hours', type=int, default=DEFAULT_OLDER_THAN_HOURS,
                        help=f'이 시간(시) 이전 수집분만 대상 (기본 {DEFAULT_OLDER_THAN_HOURS})')
    args = parser.parse_args(argv)

    junk = find_junk_ids(args.older_than_hours)
    if not junk:
        print("삭제 대상 없음 — DB가 이미 깨끗합니다.")
        return

    report(junk)

    if not args.confirm:
        print(f"\n[dry-run] 실제 삭제하려면 --confirm 플래그를 붙여 재실행하세요.")
        return

    deleted = delete_junk(junk)
    print(f"\n✅ {deleted}건 삭제 완료.")


if __name__ == '__main__':
    main()
