"""C3 청소 스크립트 안전장치 테스트.

실제 DB 접근 없이, find_junk_ids의 필터 조건(SQLAlchemy 쿼리)을 신뢰하고
report()·_batches()의 순수 로직과 main()의 --confirm 게이트를 검증한다.
이 스크립트는 이미 프로덕션에 파괴적으로 1회 실행됐으므로, "--confirm 없이는
절대 삭제하지 않는다"는 게이트가 가장 중요한 회귀 방지 대상이다.
"""
import io
import sys
import contextlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cleanup_junk_articles as cja  # noqa: E402
from cleanup_junk_articles import report, _batches  # noqa: E402


def test_report_counts_by_reason_and_shows_samples():
    junk = {
        1: ('stock_finance', '코스피 급락'),
        2: ('stock_finance', '나스닥 하락'),
        3: ('sports', '손흥민 골'),
    }
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        report(junk)
    out = buf.getvalue()
    assert '삭제 후보: 3건' in out
    assert 'stock_finance' in out and '2' in out
    assert '코스피 급락' in out or '나스닥 하락' in out


def test_report_empty_junk_no_crash():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        report({})
    assert '삭제 후보: 0건' in buf.getvalue()


# ── _batches ──────────────────────────────────────────────────────────────────

def test_batches_boundary_sizes():
    assert list(_batches([], size=500)) == []
    assert list(_batches([1], size=500)) == [[1]]
    assert list(_batches(list(range(500)), size=500)) == [list(range(500))]
    assert list(_batches(list(range(501)), size=500)) == [list(range(500)), [500]]
    assert list(_batches(list(range(1000)), size=500)) == [list(range(500)), list(range(500, 1000))]


# ── main()의 --confirm 게이트 (CRITICAL — 프로덕션 파괴적 실행 이력 있음) ──────

def test_main_without_confirm_never_deletes(monkeypatch):
    monkeypatch.setattr(cja, 'find_junk_ids', lambda hours: {1: ('stock_finance', 'x')})
    called = []
    monkeypatch.setattr(cja, 'delete_junk', lambda junk: called.append(junk) or 999)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cja.main([])  # --confirm 없음
    assert called == [], "--confirm 없이 delete_junk가 호출됨 — 안전 게이트 붕괴"
    assert '[dry-run]' in buf.getvalue()


def test_main_with_confirm_calls_delete_once(monkeypatch):
    junk = {1: ('stock_finance', 'x'), 2: ('sports', 'y')}
    monkeypatch.setattr(cja, 'find_junk_ids', lambda hours: junk)
    called = []
    monkeypatch.setattr(cja, 'delete_junk', lambda j: called.append(j) or len(j))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cja.main(['--confirm'])
    assert called == [junk]
    assert '삭제 완료' in buf.getvalue()


def test_main_no_junk_skips_report_and_delete(monkeypatch):
    monkeypatch.setattr(cja, 'find_junk_ids', lambda hours: {})
    called = []
    monkeypatch.setattr(cja, 'delete_junk', lambda j: called.append(j))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cja.main(['--confirm'])  # --confirm이어도 후보가 없으면 삭제 호출 자체가 없어야 함
    assert called == []
    assert '이미 깨끗' in buf.getvalue()
