#!/usr/bin/env python3
"""
뉴스 선별 품질 평가 스크립트 (Phase A2).

DB(Supabase 또는 로컬 SQLite)에 저장된 기사를 기간별로 조회하여
선별 파이프라인의 품질 지표를 출력한다. 선별 로직을 변경하기 전후로
실행해 수치를 비교하는 용도 — 모든 선별 개선 PR에는 이 스크립트의
전/후 결과를 첨부할 것.

지표:
  1. 비ICT 유입률  — Stage 0 필터(_collect_stage_filter_reason)가 제외했어야 할
                     기사가 DB에 얼마나 저장돼 있는가 (사유별 분포 + 샘플 제목)
  2. 선별/분석 현황 — is_selected / is_analyzed 비율
  3. 뉴스레터 충족률 — 단별·일별 분석 완료 기사 수 (목표 20개 대비)

사용법:
  python scripts/eval_selection.py                  # 최근 7일
  python scripts/eval_selection.py --days 14
  python scripts/eval_selection.py --summary "$GITHUB_STEP_SUMMARY"   # 마크다운 파일에 추가 기록

DATABASE_URL 환경변수가 있으면 Supabase(Postgres), 없으면 data/news.db 사용.
"""
import argparse
import datetime
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Windows 콘솔(cp949)에서도 이모지·불릿 출력이 깨지지 않도록 UTF-8 강제
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 프로젝트 루트를 import 경로에 추가 (scripts/ 하위에서 실행 대응)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news_engine import (  # noqa: E402
    NEWSLETTER_TARGET,          # 단별 뉴스레터 목표 기사 수 (news_engine과 단일 정의 공유)
    NewsArticle,
    get_db_session,
    get_all_units,
    _collect_stage_filter_reason,
)

KST = datetime.timezone(datetime.timedelta(hours=9))


def _kst_date(dt: datetime.datetime) -> str:
    """UTC(또는 naive) datetime → KST 날짜 문자열."""
    if dt is None:
        return '(날짜 없음)'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(KST).strftime('%Y-%m-%d')


def _sanitize_md_cell(text: str, max_len: int = 60) -> str:
    """마크다운 테이블 셀에 안전하게 넣을 수 있도록 정제.

    기사 제목은 외부 피드(RSS/Naver)에서 오는 신뢰할 수 없는 입력이므로
    파이프·개행(테이블 구조 파괴)과 HTML 태그(Actions Summary UI에 렌더링)를
    제거한다.
    """
    text = (text or '')[:max_len]
    text = text.replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    return text


def collect_metrics(days: int) -> dict:
    """최근 N일 기사에 대한 품질 지표 수집.

    collected_at은 naive UTC로 저장됨 (NewsArticle 모델 default가
    utcnow 기반) — cutoff도 naive UTC로 변환해 비교한다.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

    unit_names = {u['id']: u['display_name'] for u in get_all_units()}

    with get_db_session() as session:
        rows = (
            session.query(
                NewsArticle.id,
                NewsArticle.title,
                NewsArticle.collected_at,
                NewsArticle.is_selected,
                NewsArticle.is_analyzed,
                NewsArticle.unit_id,
                NewsArticle.unit_ids,
                NewsArticle.content,
            )
            .filter(NewsArticle.collected_at >= cutoff.replace(tzinfo=None))
            .all()
        )

    total = len(rows)
    junk_reasons: Counter = Counter()
    junk_samples: dict = defaultdict(list)
    junk_strict_total = 0
    selected = analyzed = 0
    # {(단, KST날짜): 분석 완료 수}
    unit_daily_analyzed: Counter = Counter()

    def _article_unit_ids(row) -> set:
        """주 배정(unit_id) + 다중 배정(unit_ids, ',1,2,' 형식) 통합."""
        ids = set()
        if row.unit_id:
            ids.add(row.unit_id)
        for part in (row.unit_ids or '').split(','):
            if part.strip().isdigit():
                ids.add(int(part))
        return ids

    for row in rows:
        if row.is_selected:
            selected += 1
        if row.is_analyzed:
            analyzed += 1
            uids = _article_unit_ids(row)
            if not uids:
                unit_daily_analyzed[('(미배정)', _kst_date(row.collected_at))] += 1
            for uid in uids:
                unit = unit_names.get(uid, f'단#{uid}')
                unit_daily_analyzed[(unit, _kst_date(row.collected_at))] += 1

        # 프로덕션 Stage 0은 title+summary(RSS 요약)를 입력받지만 DB에는 요약이
        # 저장되지 않는다. 두 가지 근사치를 함께 계산한다:
        #   · 제목만        → 과대 추정 (요약의 ICT 마커 화이트리스트 미반영)
        #   · 제목+본문 일부 → 과소 추정 (본문 노이즈가 화이트리스트를 과발동)
        # 실제 유입률은 두 값 사이에 있다.
        reason_title = _collect_stage_filter_reason({'title': row.title or ''})
        reason_strict = _collect_stage_filter_reason({
            'title': row.title or '',
            'summary': (row.content or '')[:300],
        })
        if reason_title:
            junk_reasons[reason_title] += 1
            if len(junk_samples[reason_title]) < 3:
                junk_samples[reason_title].append(_sanitize_md_cell(row.title))
        if reason_strict:
            junk_strict_total += 1

    junk_total = sum(junk_reasons.values())
    return {
        'days': days,
        'total': total,
        'junk_total': junk_total,
        'junk_rate': (junk_total / total * 100) if total else 0.0,
        'junk_strict_total': junk_strict_total,
        'junk_strict_rate': (junk_strict_total / total * 100) if total else 0.0,
        'junk_reasons': junk_reasons,
        'junk_samples': junk_samples,
        'selected': selected,
        'analyzed': analyzed,
        'unit_daily_analyzed': unit_daily_analyzed,
        'unit_names': sorted(set(unit_names.values())),
        'units_lookup_failed': not unit_names,
    }


def render_markdown(m: dict) -> str:
    """지표 → 마크다운 리포트."""
    lines = []
    lines.append(f"## 📊 선별 품질 리포트 (최근 {m['days']}일)")
    lines.append("")
    if m.get('units_lookup_failed'):
        lines.append("> ⚠️ units 테이블 조회 실패 — 단 이름이 `단#N` 형식으로 표시됩니다.")
        lines.append("")
    lines.append("| 지표 | 값 |")
    lines.append("|------|-----|")
    lines.append(f"| 저장 기사 수 | {m['total']}개 |")
    lines.append(f"| **비ICT 유입 상한 (제목만 판정)** | **{m['junk_total']}개 ({m['junk_rate']:.1f}%)** |")
    lines.append(f"| 비ICT 유입 하한 (제목+본문 판정) | {m['junk_strict_total']}개 ({m['junk_strict_rate']:.1f}%) |")
    lines.append(f"| AI 선별 (is_selected) | {m['selected']}개 |")
    lines.append(f"| 심층 분석 완료 (is_analyzed) | {m['analyzed']}개 |")
    lines.append("")

    if m['junk_reasons']:
        lines.append("### 비ICT 유입 사유별 분포")
        lines.append("")
        lines.append("| 사유 | 건수 | 샘플 제목 |")
        lines.append("|------|------|-----------|")
        for reason, count in m['junk_reasons'].most_common(10):
            sample = m['junk_samples'][reason][0] if m['junk_samples'][reason] else ''
            lines.append(f"| {reason} | {count} | {sample} |")
        lines.append("")

    # 단별·일별 뉴스레터 충족률 (최근 날짜부터)
    # 열은 전체 단 목록 기준 — 분석 0건인 단도 ❌로 드러나야 함 (완전 결측 감지)
    daily = m['unit_daily_analyzed']
    if daily:
        dates = sorted({d for (_, d) in daily}, reverse=True)
        units = sorted(set(m['unit_names']) | {u for (u, _) in daily})
        lines.append(f"### 단별 뉴스레터 충족률 (분석 완료 기사 수 / 목표 {NEWSLETTER_TARGET}개)")
        lines.append("")
        lines.append("| 날짜(KST) | " + " | ".join(units) + " |")
        lines.append("|" + "---|" * (len(units) + 1))
        for d in dates:
            cells = []
            for u in units:
                n = daily.get((u, d), 0)
                mark = "" if n >= NEWSLETTER_TARGET else " ⚠️" if n > 0 else " ❌"
                cells.append(f"{n}{mark}")
            lines.append(f"| {d} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append(f"(⚠️ = {NEWSLETTER_TARGET}개 미달, ❌ = 0개)")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='뉴스 선별 품질 평가')
    parser.add_argument('--days', type=int, default=7, choices=range(1, 91),
                        metavar='1-90', help='조회 기간 (일, 기본 7, 최대 90 — 전체 로드 방지)')
    parser.add_argument('--summary', type=str, default='',
                        help='마크다운 리포트를 추가 기록할 파일 경로 (예: $GITHUB_STEP_SUMMARY)')
    args = parser.parse_args()

    metrics = collect_metrics(args.days)
    report = render_markdown(metrics)
    print(report)

    if args.summary:
        try:
            with open(args.summary, 'a', encoding='utf-8') as f:
                f.write(report + "\n")
            print(f"\n(리포트를 {args.summary}에 기록했습니다)")
        except OSError as e:
            print(f"\n(경고) summary 파일 기록 실패: {e}")


if __name__ == '__main__':
    main()
