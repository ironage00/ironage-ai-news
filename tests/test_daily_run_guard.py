"""daily_run_guard — 같은 날 일일 파이프라인 중복 실행 방지."""
import datetime as dt
import threading

import pytest
from sqlalchemy import create_engine, text

from daily_run_guard import COMPLETED, FAILED, PARTIAL, STALE_RUNNING, claim_daily_run, finish_daily_run

KST = dt.timezone(dt.timedelta(hours=9))
T0 = dt.datetime(2026, 11, 27, 8, 25, tzinfo=KST)
DAY = "2026-11-27"


@pytest.fixture
def engine(tmp_path):
    return create_engine(f"sqlite:///{(tmp_path / 'guard.db').as_posix()}")


def _status(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT status FROM daily_run_marker WHERE run_date = :d"), {"d": DAY}).scalar()


def _run(engine, status, at=T0, minutes=18):
    ok, _, token = claim_daily_run(engine, DAY, at)
    assert ok
    assert finish_daily_run(engine, DAY, status, at + dt.timedelta(minutes=minutes), "", token)
    return token


def test_first_run_proceeds_and_records_running(engine):
    ok, why, token = claim_daily_run(engine, DAY, T0)
    assert ok and "첫 실행" in why and token
    assert _status(engine) == "running"


def test_second_trigger_after_completion_is_skipped(engine):
    _run(engine, COMPLETED)
    ok, why, token = claim_daily_run(engine, DAY, T0 + dt.timedelta(hours=8))
    assert not ok and "이미 완료" in why and token is None
    assert _status(engine) == COMPLETED


def test_trigger_while_running_is_skipped(engine):
    claim_daily_run(engine, DAY, T0)
    ok, why, _ = claim_daily_run(engine, DAY, T0 + dt.timedelta(minutes=5))
    assert not ok and "진행 중" in why


def test_force_never_takes_over_an_active_run(engine):
    claim_daily_run(engine, DAY, T0)
    ok, why, _ = claim_daily_run(engine, DAY, T0 + dt.timedelta(minutes=5), force=True)
    assert not ok and "진행 중" in why


def test_stuck_running_is_retried_after_stale_window(engine):
    claim_daily_run(engine, DAY, T0)
    ok, why, _ = claim_daily_run(engine, DAY, T0 + STALE_RUNNING + dt.timedelta(minutes=1))
    assert ok and "멈춘" in why


def test_failed_before_sending_can_be_retried(engine):
    _run(engine, FAILED, minutes=3)
    ok, why, _ = claim_daily_run(engine, DAY, T0 + dt.timedelta(minutes=30))
    assert ok and "실패" in why
    assert _status(engine) == "running"


def test_partial_send_is_not_retried_automatically(engine):
    _run(engine, PARTIAL)
    ok, why, _ = claim_daily_run(engine, DAY, T0 + dt.timedelta(hours=1))
    assert not ok and "일부 발송" in why
    ok, why, _ = claim_daily_run(engine, DAY, T0 + dt.timedelta(hours=1), force=True)
    assert ok and "강제" in why


def test_force_reruns_a_completed_day(engine):
    _run(engine, COMPLETED)
    ok, why, _ = claim_daily_run(engine, DAY, T0 + dt.timedelta(hours=1), force=True)
    assert ok and "강제" in why


def test_old_run_cannot_overwrite_after_takeover(engine):
    _, _, old_token = claim_daily_run(engine, DAY, T0)
    ok, _, new_token = claim_daily_run(engine, DAY, T0 + STALE_RUNNING + dt.timedelta(minutes=1))
    assert ok and new_token != old_token
    # 넘겨받힌 옛 실행이 나중에 실패로 끝나도 새 실행 기록은 그대로
    assert not finish_daily_run(engine, DAY, FAILED, T0 + STALE_RUNNING + dt.timedelta(minutes=2), "late", old_token)
    assert _status(engine) == "running"
    assert finish_daily_run(engine, DAY, COMPLETED, T0 + STALE_RUNNING + dt.timedelta(minutes=20), "", new_token)
    assert _status(engine) == COMPLETED


def test_next_day_is_independent(engine):
    _run(engine, COMPLETED)
    ok, _, _ = claim_daily_run(engine, "2026-11-28", T0 + dt.timedelta(days=1))
    assert ok


def test_concurrent_claims_only_one_wins(engine):
    _run(engine, FAILED, minutes=3)
    results = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        results.append(claim_daily_run(engine, DAY, T0 + dt.timedelta(minutes=10))[0])

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1


# ── news_engine 통합: 결과 판정과 공용 진입점 ─────────────────────────────

def test_daily_run_outcome_rules(monkeypatch):
    from news_engine import daily_run_outcome
    monkeypatch.delenv("DISABLE_EMAIL", raising=False)
    weekday = dict(sends_expected=True)
    assert daily_run_outcome(4, [], crashed=False, **weekday) == COMPLETED           # 전부 전달
    assert daily_run_outcome(0, ["a", "b"], crashed=False, **weekday) == FAILED      # 전부 실패(전달 0) → 재시도
    assert daily_run_outcome(0, [], crashed=False, **weekday) == FAILED              # 평일인데 한 통도 안 감 → 재시도
    assert daily_run_outcome(2, ["a"], crashed=False, **weekday) == PARTIAL          # 일부 전달 + 실패 → 재발송 금지
    assert daily_run_outcome(1, ["a"], crashed=False, **weekday) == PARTIAL          # 수신 일부 거부(전달됐지만 실패 판정)
    assert daily_run_outcome(0, [], crashed=True, **weekday) == FAILED               # 발송 전 중단
    assert daily_run_outcome(2, [], crashed=True, **weekday) == PARTIAL              # 발송 후 중단
    assert daily_run_outcome(0, [], crashed=False, sends_expected=False) == COMPLETED  # 주말 정상 종료
    monkeypatch.setenv("DISABLE_EMAIL", "1")
    assert daily_run_outcome(0, [], crashed=False, sends_expected=False) == FAILED   # 메일 끈 시험 실행은 실제 실행을 막지 않음


@pytest.fixture
def guarded(monkeypatch, tmp_path):
    import news_engine
    eng = create_engine(f"sqlite:///{(tmp_path / 'ne_guard.db').as_posix()}")
    monkeypatch.setattr(news_engine, "DB_ENGINE", eng)
    monkeypatch.setattr(news_engine, "daily_sends_expected", lambda: True)  # 평일 실행으로 고정
    calls = {"n": 0, "mode": "ok"}

    def fake_pipeline(ai_model=None):
        calls["n"] += 1
        mode = calls["mode"]
        if mode in ("ok", "refused", "crash_after_send"):
            news_engine.DAILY_RUN_STATE["newsletter_delivered"] += 2
        if mode == "crash_after_send":
            raise RuntimeError("boom")
        errors = ["이메일 발송 실패"] if mode in ("outage", "refused") else []
        return {"단A": {"errors": errors}, "단B": {"errors": list(errors)}}

    monkeypatch.setattr(news_engine, "run_all_units_daily", fake_pipeline)
    return news_engine, calls, eng


def test_guarded_pipeline_runs_once_per_day(guarded):
    ne, calls, _ = guarded
    assert ne.run_daily_pipeline_guarded()["skipped"] is False
    second = ne.run_daily_pipeline_guarded()
    assert second["skipped"] is True and calls["n"] == 1
    assert ne.run_daily_pipeline_guarded(force=True)["skipped"] is False and calls["n"] == 2


def test_total_mail_outage_stays_retryable(guarded):
    ne, calls, _ = guarded
    calls["mode"] = "outage"  # SMTP 로그인 실패 등: 전달 0
    assert ne.run_daily_pipeline_guarded()["mail_failures"] == ["단A", "단B"]
    calls["mode"] = "ok"
    assert ne.run_daily_pipeline_guarded()["skipped"] is False and calls["n"] == 2


def test_partial_recipient_refusal_blocks_automatic_retry(guarded):
    ne, calls, _ = guarded
    calls["mode"] = "refused"  # 일부 수신 거부: 실패 판정이지만 나머지는 이미 받음
    ne.run_daily_pipeline_guarded()
    calls["mode"] = "ok"
    assert ne.run_daily_pipeline_guarded()["skipped"] is True and calls["n"] == 1


def test_crash_after_sending_blocks_automatic_retry(guarded):
    ne, calls, _ = guarded
    calls["mode"] = "crash_after_send"
    with pytest.raises(RuntimeError):
        ne.run_daily_pipeline_guarded()
    calls["mode"] = "ok"
    assert ne.run_daily_pipeline_guarded()["skipped"] is True and calls["n"] == 1


def test_zero_delivery_weekday_run_is_retryable(guarded):
    ne, calls, _ = guarded
    calls["mode"] = "nothing"  # 수집·분석 실패로 보낼 기사가 없던 평일
    ne.run_daily_pipeline_guarded()
    calls["mode"] = "ok"
    assert ne.run_daily_pipeline_guarded()["skipped"] is False and calls["n"] == 2


def test_email_disabled_matches_sender_rule(monkeypatch):
    from news_engine import email_disabled
    for value in ("1", "true", "YES", " on "):
        monkeypatch.setenv("DISABLE_EMAIL", value)
        assert email_disabled()
    for value in ("", "0", "false"):
        monkeypatch.setenv("DISABLE_EMAIL", value)
        assert not email_disabled()
