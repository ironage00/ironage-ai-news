"""일일 파이프라인(news_engine.py daily) 중복 실행 방지.

2026-11-26: 예전 가드(최근 20시간 분석 기사 5건 이상이면 건너뜀)는 레거시
run_daily_collection()에만 있어, 실제로 쓰는 run_all_units_daily() 경로에서는
작동하지 않았다. cron-job.org가 두 번 호출하거나 수동으로 다시 돌리면 전체 수집이
다시 돌고 뉴스레터가 두 번 나갈 수 있었다.

날짜(KST)별로 한 줄을 남긴다:
  running   — 실행 중. STALE_RUNNING보다 오래되면(러너 강제 종료 등) 다른 실행이 넘겨받는다.
              진행 중(오래되지 않음)이면 force로도 넘겨받지 않는다(동시 발송 방지).
  completed — 끝남. 같은 날 다시 실행하지 않는다(force로만 가능).
  partial   — 뉴스레터 일부를 보낸 뒤 중단. 자동 재실행하면 중복 발송되므로 force로만 가능.
  failed    — 뉴스레터를 보내기 전에 중단. 다시 실행 허용.
같은 날짜를 동시에 잡으려 하면 기본키 충돌·조건부 갱신으로 한쪽만 이긴다.
claim이 돌려준 토큰(시작 시각)을 가진 실행만 상태를 마무리할 수 있다 — 넘겨받힌 옛 실행이
나중에 끝나도 새 실행의 기록을 덮어쓰지 못한다.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

RUNNING, COMPLETED, PARTIAL, FAILED = "running", "completed", "partial", "failed"
# daily-collection.yml timeout-minutes(150)보다 길게 — 정상 실행 중인 run을 'stale'로 오판하지 않도록.
STALE_RUNNING = _dt.timedelta(hours=4)

_CREATE = """
CREATE TABLE IF NOT EXISTS daily_run_marker (
    run_date    VARCHAR(10) PRIMARY KEY,
    status      VARCHAR(20) NOT NULL,
    started_at  VARCHAR(40),
    finished_at VARCHAR(40),
    detail      TEXT
)
"""


def _iso(value: _dt.datetime) -> str:
    return value.isoformat(timespec="microseconds")


def _parse(value) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def claim_daily_run(engine: Engine, run_date: str, now: _dt.datetime, force: bool = False) -> tuple[bool, str, str | None]:
    """(진행 여부, 사유, 토큰)을 반환한다. 진행하면 상태를 running으로 기록하고 토큰(시작 시각)을 준다.
    건너뛰면 아무것도 바꾸지 않고 토큰은 None."""
    token = _iso(now)
    with engine.begin() as conn:
        conn.execute(text(_CREATE))
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO daily_run_marker (run_date, status, started_at) VALUES (:d, :s, :t)"),
                {"d": run_date, "s": RUNNING, "t": token},
            )
        return True, f"{run_date} 첫 실행", token
    except IntegrityError:
        pass  # 같은 날짜 기록이 이미 있음 — 아래에서 상태를 보고 판단

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT status, started_at FROM daily_run_marker WHERE run_date = :d"), {"d": run_date}
        ).first()
        status, started_at = (row[0], row[1]) if row else (None, None)
        started = _parse(started_at)
        active = status == RUNNING and (started is None or now - started < STALE_RUNNING)
        if active:  # force로도 진행 중인 실행은 넘겨받지 않는다
            return False, f"{run_date} 실행이 진행 중({started_at} 시작)", None
        if not force and status == COMPLETED:
            return False, f"{run_date} 실행이 이미 완료됨({started_at} 시작)", None
        if not force and status == PARTIAL:
            return False, f"{run_date} 실행이 뉴스레터 일부 발송 후 중단됨 — 중복 발송 위험으로 자동 재실행 안 함", None
        # 조건부 갱신: 그사이 다른 실행이 상태를 바꿨다면 0건 갱신 → 건너뜀
        updated = conn.execute(
            text(
                "UPDATE daily_run_marker SET status = :new, started_at = :t, finished_at = NULL, detail = NULL "
                "WHERE run_date = :d AND status = :old AND started_at = :prev"
            ),
            {"new": RUNNING, "t": token, "d": run_date, "old": status, "prev": started_at},
        ).rowcount
    if updated != 1:
        return False, f"{run_date} 실행 상태가 동시에 바뀜 — 다른 실행에 양보", None
    reason = {
        FAILED: "이전 실행 실패 후 재실행",
        RUNNING: "이전 실행이 멈춘 것으로 보고 재실행",
        COMPLETED: "강제 재실행",
        PARTIAL: "강제 재실행(일부 발송 이력 있음)",
    }.get(status, "재실행")
    return True, f"{run_date} {reason}", token


def finish_daily_run(engine: Engine, run_date: str, status: str, now: _dt.datetime, detail: str, token: str) -> bool:
    """토큰을 가진 실행만 running 상태를 마무리한다. 실제로 바꿨으면 True."""
    with engine.begin() as conn:
        updated = conn.execute(
            text(
                "UPDATE daily_run_marker SET status = :s, finished_at = :t, detail = :x "
                "WHERE run_date = :d AND status = :running AND started_at = :token"
            ),
            {"s": status, "t": _iso(now), "x": (detail or "")[:1000], "d": run_date, "running": RUNNING, "token": token},
        ).rowcount
    return updated == 1
