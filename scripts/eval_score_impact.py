"""선별점수 × impact_level 상관 분석 — 심층분석 앞단 게이트 컷 확정용.

score_impact_samples 표본(매 daily 실행이 누적)을 읽어:
  (a) 선별점수 분포
  (b) 혼동행렬: score{1..5, 미선별} × impact{Critical/High/Medium/Low}
  (c) 컷별(score>=3/4/5) 시뮬레이션 — 심층분석 물량·단별 잔존·회귀위험(고impact인데
      저score = 게이트가 잘못 버릴 기사)

사용법:
    python scripts/eval_score_impact.py [--days 14] [--summary $GITHUB_STEP_SUMMARY]

컷 확정 기준(권장): Critical/High false-negative(잘못 버릴 기사) 비율이 허용선
(예: 5%) 이하인 '가장 높은' 컷을 선택. 표본이 얇으면(<300) 판단 보류.
"""
import argparse
import datetime
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:  # Windows 콘솔(cp949) 이모지 출력 방어
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import news_engine as ne  # noqa: E402

_UNIT = {1: '표준기획', 2: '표준혁신', 3: 'AI융합', 4: '전파네트워크'}
_IMPACTS = ['Critical', 'High', 'Medium', 'Low']
_HIGH = {'Critical', 'High'}


def _load(days):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    with ne.get_db_session() as s:
        rows = (s.query(ne.ScoreImpactSample)
                  .filter(ne.ScoreImpactSample.run_ts >= cutoff.replace(tzinfo=None))
                  .all())
        # 세션 밖 사용 위해 값만 추출
        return [(r.phase26_score, bool(r.was_selected), r.impact_level, r.unit_id, r.run_date)
                for r in rows]


def _bucket(score, was_selected):
    return str(score) if was_selected and score is not None else '미선별'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--summary', type=str, default='')
    args = ap.parse_args(argv)

    rows = _load(args.days)
    out = []
    def emit(line=''):
        out.append(line)
        print(line)

    emit(f"## 📊 선별점수 × impact 상관 (최근 {args.days}일)")
    emit()
    if not rows:
        emit("표본 없음 — 계측 누적 후 재실행.")
        _write(args.summary, out)
        return
    dates = sorted({r[4] for r in rows})
    emit(f"- 표본 {len(rows)}개, {len(dates)}일치 ({dates[0]}~{dates[-1]})")
    if len(rows) < 300:
        emit(f"- ⚠️ 표본 부족(<300) — 방향 감만, 컷 확정은 보류 권장")
    emit()

    # (a) 선별점수 분포
    emit("### (a) 선별점수 분포 (선별된 기사)")
    sc = Counter(r[0] for r in rows if r[1] and r[0] is not None)
    emit('| score | ' + ' | '.join(str(k) for k in sorted(sc)) + ' |')
    emit('|---|' + '---|' * len(sc))
    emit('| 건수 | ' + ' | '.join(str(sc[k]) for k in sorted(sc)) + ' |')
    emit(f"- 미선별(점수 없음): {sum(1 for r in rows if not r[1])}개")
    emit()

    # (b) 혼동행렬
    emit("### (b) 혼동행렬: score × impact")
    matrix = defaultdict(Counter)
    for score, wsel, impact, _u, _d in rows:
        matrix[_bucket(score, wsel)][impact or 'Medium'] += 1
    buckets = ['5', '4', '3', '2', '1', '미선별']
    emit('| score \\ impact | ' + ' | '.join(_IMPACTS) + ' | 합 |')
    emit('|---|' + '---|' * (len(_IMPACTS) + 1))
    for b in buckets:
        if b not in matrix:
            continue
        row = matrix[b]
        tot = sum(row.values())
        emit(f'| **{b}** | ' + ' | '.join(str(row.get(i, 0)) for i in _IMPACTS) + f' | {tot} |')
    emit()

    # (c) 컷별 시뮬레이션
    emit("### (c) 컷별 시뮬레이션 (score≥컷만 심층분석 게이트 통과 가정)")
    total_highimpact = sum(1 for r in rows if (r[2] in _HIGH))
    emit(f"- 전체 표본 중 고impact(Critical/High): {total_highimpact}개")
    emit()
    emit('| 컷 | 통과(분석대상) | 물량비 | 단별 잔존 | 회귀위험(고impact 탈락) |')
    emit('|---|---|---|---|---|')
    n_all = len(rows)
    for cut in [3, 4, 5]:
        passed = [r for r in rows if (r[1] and r[0] is not None and r[0] >= cut)]
        # 회귀위험: 컷 미달(미선별 포함)인데 impact가 고impact인 기사
        dropped_high = sum(1 for r in rows
                           if not (r[1] and r[0] is not None and r[0] >= cut)
                           and r[2] in _HIGH)
        by_unit = defaultdict(int)
        for r in passed:
            by_unit[r[3]] += 1
        unit_str = ' '.join(f'{_UNIT.get(u, u)}={by_unit.get(u, 0)}' for u in [1, 2, 3, 4])
        fn_ratio = (dropped_high / total_highimpact * 100) if total_highimpact else 0
        emit(f'| score≥{cut} | {len(passed)} | {len(passed)/n_all*100:.0f}% | {unit_str} | '
             f'{dropped_high}건 ({fn_ratio:.0f}%) |')
    emit()
    emit("**컷 확정 가이드**: 회귀위험(고impact 탈락 비율)이 허용선(예:5%) 이하인 "
         "가장 높은 컷 선택. 표준기획 잔존 0이면 그 컷은 과함.")

    _write(args.summary, out)


def _write(path, lines):
    if path:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        except Exception as e:
            print(f"summary 기록 실패: {e}")


if __name__ == '__main__':
    main()
