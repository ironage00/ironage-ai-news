"""섀도 발송(SHADOW_RECEIVERS): 구독자 대신 시험 수신자에게만 보내는 실행.

2026-11-28: Gmail 앱 비밀번호 교체 뒤 실제 구독자에게 보내기 전에 한 사람에게만 시험 발송하기 위해 추가.
지켜야 할 것: ① 구독자에게는 절대 가지 않는다 ② 주소가 잘못되면 구독자로 되돌아가지 않고 멈춘다
③ 그날의 실행 기록(중복 발송 방지)을 건드리지 않는다.
"""
import pytest
from sqlalchemy import create_engine

import news_engine


class FakeSMTP:
    sent = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def sendmail(self, sender, receivers, message):
        FakeSMTP.sent.append((list(receivers), message))
        return {}


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(news_engine.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(news_engine, "SENDER_EMAIL", "sender@example.com")
    monkeypatch.setattr(news_engine, "GMAIL_PASSWORD", "x")
    monkeypatch.delenv("DISABLE_EMAIL", raising=False)
    news_engine.DAILY_RUN_STATE["newsletter_delivered"] = 0
    return FakeSMTP


def _send():
    return news_engine.send_gmail_report(
        "시험 보고서", [], None, [], receivers=["sub1@tta.or.kr", "sub2@tta.or.kr"], unit_display="표준기획단")


def test_shadow_receivers_parses_and_rejects_bad_addresses(monkeypatch):
    monkeypatch.delenv("SHADOW_RECEIVERS", raising=False)
    assert news_engine.shadow_mode() is False and news_engine.shadow_receivers() == []
    monkeypatch.setenv("SHADOW_RECEIVERS", " me@tta.or.kr , me@tta.or.kr,you@tta.or.kr ")
    assert news_engine.shadow_mode() is True
    assert news_engine.shadow_receivers() == ["me@tta.or.kr", "you@tta.or.kr"]
    monkeypatch.setenv("SHADOW_RECEIVERS", "me@tta.or.kr, not-an-address")
    assert news_engine.shadow_mode() is True and news_engine.shadow_receivers() == []


def test_normal_send_goes_to_subscribers_and_counts(smtp, monkeypatch):
    monkeypatch.delenv("SHADOW_RECEIVERS", raising=False)
    assert _send() is True
    assert smtp.sent[0][0] == ["sub1@tta.or.kr", "sub2@tta.or.kr"]
    assert news_engine.DAILY_RUN_STATE["newsletter_delivered"] == 1


def test_shadow_send_goes_only_to_shadow_receiver(smtp, monkeypatch):
    monkeypatch.setenv("SHADOW_RECEIVERS", "me@tta.or.kr")
    assert _send() is True
    receivers, message = smtp.sent[0]
    assert receivers == ["me@tta.or.kr"]
    assert "sub1@tta.or.kr" not in message and "sub2@tta.or.kr" not in message
    assert news_engine.DAILY_RUN_STATE["newsletter_delivered"] == 0  # 구독자가 받은 게 아니다


def test_bad_shadow_address_sends_to_nobody(smtp, monkeypatch):
    monkeypatch.setenv("SHADOW_RECEIVERS", "오타주소")
    assert _send() is False
    assert smtp.sent == []


def test_shadow_run_leaves_daily_run_record_alone(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'shadow_guard.db').as_posix()}")
    monkeypatch.setattr(news_engine, "DB_ENGINE", eng)
    monkeypatch.setattr(news_engine, "daily_sends_expected", lambda: True)
    calls = {"n": 0}

    def fake_pipeline(ai_model=None):
        calls["n"] += 1
        if not news_engine.shadow_mode():
            news_engine.DAILY_RUN_STATE["newsletter_delivered"] += 2
        return {"단A": {"errors": []}}

    monkeypatch.setattr(news_engine, "run_all_units_daily", fake_pipeline)

    # 섀도를 먼저 돌려도 그날의 실제 실행을 막지 않는다
    monkeypatch.setenv("SHADOW_RECEIVERS", "me@tta.or.kr")
    assert news_engine.run_daily_pipeline_guarded()["skipped"] is False
    monkeypatch.delenv("SHADOW_RECEIVERS")
    assert news_engine.run_daily_pipeline_guarded()["skipped"] is False
    # 실제 실행이 끝난 뒤 섀도를 돌려도 실제 실행이 다시 열리지 않는다
    monkeypatch.setenv("SHADOW_RECEIVERS", "me@tta.or.kr")
    assert news_engine.run_daily_pipeline_guarded()["skipped"] is False
    monkeypatch.delenv("SHADOW_RECEIVERS")
    assert news_engine.run_daily_pipeline_guarded()["skipped"] is True
    assert calls["n"] == 3
