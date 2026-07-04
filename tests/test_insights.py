"""인사이트 파이프라인 테스트 — 운영 알림(α)·내러티브(β)·클러스터/타임라인(γ).

네트워크·DB·실제 AI 호출은 다루지 않는다. 순수 함수 + monkeypatch 검증.
"""
import news_engine
from news_engine import (
    _detect_pipeline_anomalies,
    _ops_email_receivers,
    _ops_alert,
    OPS_ALERT_EMAIL_DEFAULT,
)


# ── _detect_pipeline_anomalies (α: 배정 수 이상탐지) ─────────────────────────

_NAMES = {1: '표준기획단', 2: '표준혁신단'}


def test_anomaly_detects_sharp_drop():
    """표준기획단 37→1 시나리오 — 반드시 경고가 나와야 한다."""
    today = {1: {'phase2': 1, 'analyzed': 10}}
    prev = {1: {'phase2': 37, 'analyzed': 12}}
    warns = _detect_pipeline_anomalies(today, prev, _NAMES)
    assert any('급감' in w and '표준기획단' in w for w in warns)


def test_anomaly_detects_sharp_spike():
    today = {2: {'phase2': 300, 'analyzed': 20}}
    prev = {2: {'phase2': 60, 'analyzed': 20}}
    warns = _detect_pipeline_anomalies(today, prev, _NAMES)
    assert any('급증' in w for w in warns)


def test_anomaly_ignores_small_pool_noise():
    """작은 풀의 절대 변화량이 min_delta 미만이면 비율이 커도 무시 (노이즈 방지)."""
    today = {1: {'phase2': 2, 'analyzed': 10}}
    prev = {1: {'phase2': 6, 'analyzed': 10}}   # -67%지만 절대 변화 4건
    warns = _detect_pipeline_anomalies(today, prev, _NAMES)
    assert not any('급감' in w for w in warns)


def test_anomaly_no_prev_data_skips_comparison():
    """첫 실행(전일 데이터 없음)엔 변동률 경고 없음 — 게재 수 미달만 검사."""
    today = {1: {'phase2': 50, 'analyzed': 15}}
    warns = _detect_pipeline_anomalies(today, {}, _NAMES)
    assert warns == []


def test_anomaly_low_final_count_warns_regardless_of_prev():
    today = {1: {'phase2': 40, 'analyzed': 2}}
    warns = _detect_pipeline_anomalies(today, {}, _NAMES)
    assert any('게재 2건' in w for w in warns)


def test_anomaly_normal_day_is_quiet():
    today = {1: {'phase2': 40, 'analyzed': 18}, 2: {'phase2': 65, 'analyzed': 20}}
    prev = {1: {'phase2': 38, 'analyzed': 17}, 2: {'phase2': 70, 'analyzed': 20}}
    assert _detect_pipeline_anomalies(today, prev, _NAMES) == []


# ── _ops_email_receivers / _ops_alert (α: 관리자 통보) ───────────────────────

def test_ops_receivers_default(monkeypatch):
    monkeypatch.delitem(news_engine.CONFIG, 'ops_alert_email', raising=False)
    assert _ops_email_receivers() == [OPS_ALERT_EMAIL_DEFAULT]


def test_ops_receivers_config_override_comma_separated(monkeypatch):
    monkeypatch.setitem(news_engine.CONFIG, 'ops_alert_email', 'a@tta.or.kr, b@tta.or.kr')
    assert _ops_email_receivers() == ['a@tta.or.kr', 'b@tta.or.kr']


def test_ops_alert_disabled_sends_nothing(monkeypatch):
    sent = []
    monkeypatch.setattr(news_engine, '_send_admin_email', lambda *a, **k: sent.append(a) or True)
    monkeypatch.setitem(news_engine.CONFIG, 'ops_alert_enabled', False)
    _ops_alert('테스트', ['내용'])
    assert sent == []


def test_ops_alert_sends_email(monkeypatch):
    sent = []
    monkeypatch.setattr(news_engine, '_send_admin_email',
                        lambda subject, body: sent.append((subject, body)) or True)
    monkeypatch.setitem(news_engine.CONFIG, 'ops_alert_enabled', True)
    monkeypatch.setitem(news_engine.CONFIG, 'google_chat_webhook', '')
    _ops_alert('선별 실패', ['오류: timeout', '후보 289개'], severity='critical')
    assert len(sent) == 1
    subject, body = sent[0]
    assert '선별 실패' in subject and '🚨' in subject
    assert 'timeout' in body and '289' in body


def test_ops_alert_accepts_plain_string_detail(monkeypatch):
    sent = []
    monkeypatch.setattr(news_engine, '_send_admin_email',
                        lambda subject, body: sent.append(body) or True)
    monkeypatch.setitem(news_engine.CONFIG, 'ops_alert_enabled', True)
    monkeypatch.setitem(news_engine.CONFIG, 'google_chat_webhook', '')
    _ops_alert('제목', '문자열 하나만 전달')
    assert len(sent) == 1 and '문자열 하나만' in sent[0]
