"""scripts/eval_selection.py의 Phase 2.6 섀도 집계 검증.

collect_metrics()가 SelectionLog를 올바르게 집계하는지, 임시 DB(conftest.py가
세션 전체를 고정한 SQLite)에 직접 행을 넣어 확인한다.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import eval_selection  # noqa: E402
from news_engine import SelectionLog, get_db_session  # noqa: E402


def _add_log(mode, link, selected, unit_ids_str, score=None, reason=''):
    with get_db_session() as s:
        s.add(SelectionLog(
            mode=mode, ai_model='openai', link=link, title=link,
            score=score, reason=reason, selected=selected,
            unit_ids_str=unit_ids_str,
        ))
        s.commit()


def test_shadow_daily_counts_include_floor_supplement(monkeypatch):
    """selected=False(하한 보장 보충)도 '전환 시 남는 기사 수'에 포함돼야 한다.

    news_engine.py의 run_phase26_selection() 수정(섀도 모드도 supplemented를
    selection_log에 함께 남기도록 함)과 짝을 이루는 리포트 쪽 검증 — 수정 전
    eval_selection.py는 selected=True인 행만 세서 하한 보충분이 리포트에서
    통째로 빠졌었다.
    """
    # 다른 테스트/실행과 절대 겹치지 않도록 이 테스트 전용 단 ID 사용
    uid = 90000 + (uuid.uuid4().int % 9000)
    monkeypatch.setattr(eval_selection, 'get_all_units',
                        lambda: [{'id': uid, 'display_name': f'테스트단{uid}'}])

    link_prefix = uuid.uuid4().hex[:8]
    _add_log('shadow', f'{link_prefix}-sel1', selected=True,
             unit_ids_str=f',{uid},', score=5, reason='FCC 규제')
    _add_log('shadow', f'{link_prefix}-supp1', selected=False,
             unit_ids_str=f',{uid},', reason='하한 보장 보충')
    _add_log('shadow', f'{link_prefix}-supp2', selected=False,
             unit_ids_str=f',{uid},', reason='하한 보장 보충')

    metrics = eval_selection.collect_metrics(days=7)
    shadow_daily = metrics['shadow_daily']
    unit_name = f'테스트단{uid}'
    total = sum(v for (unit, _date), v in shadow_daily.items() if unit == unit_name)
    assert total == 3   # AI 선별 1 + 하한 보충 2 = 활성 전환 시 남는 3건


def test_shadow_reasons_only_use_selected_rows(monkeypatch):
    """고득점 사유 샘플은 실제 AI 선별(score 보유) 행에서만 뽑고, score가
    없는 하한 보충 행은 절대 섞이지 않는다."""
    uid = 80000 + (uuid.uuid4().int % 9000)
    monkeypatch.setattr(eval_selection, 'get_all_units',
                        lambda: [{'id': uid, 'display_name': f'테스트단{uid}'}])

    link_prefix = uuid.uuid4().hex[:8]
    _add_log('shadow', f'{link_prefix}-sel1', selected=True,
             unit_ids_str=f',{uid},', score=5, reason='국제표준화 핵심 이슈')
    _add_log('shadow', f'{link_prefix}-supp1', selected=False,
             unit_ids_str=f',{uid},', reason='하한 보장 보충')

    metrics = eval_selection.collect_metrics(days=7)
    assert any('국제표준화 핵심 이슈' in r for r in metrics['shadow_reasons'])
    assert not any('하한 보장 보충' in r for r in metrics['shadow_reasons'])
