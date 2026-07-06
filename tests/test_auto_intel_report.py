"""주간/월간 자율 인텔리전스 리포트 이메일 발송 회귀 테스트.

배경: 2026-07-03 auto_intel_report.py 전환(PR #12) 당시 node_send_report가
send_trend_report_email()을 receivers 인자 없이 호출하도록 구현되어, 레거시
run_weekly_report()가 쓰던 get_weekly_subscribers() 취합 로직(단별 email_recipients
전체, 약 45명)이 누락됨 — 실제로는 전역 GMAIL_SENDER 1명에게만 조용히 발송되는
회귀가 2026-07-06 첫 주간 실행에서 발견됨. 이 파일은 그 재발을 막는다.
"""
import sys
import types

import auto_intel_report
import news_engine


def _base_state(period='weekly'):
    state = auto_intel_report.make_state(period=period)
    state['doc_url'] = 'https://docs.google.com/fake'
    state['analysis_result'] = {'summary': 'ok'}
    state['report_title'] = '테스트 리포트'
    state['surges'] = []
    return state


def test_send_report_passes_full_subscriber_list(monkeypatch):
    """node_send_report는 반드시 get_weekly_subscribers() 결과를 receivers로 전달해야 한다."""
    fake_subs = [f"user{i}@tta.or.kr" for i in range(45)]
    monkeypatch.setattr(auto_intel_report, 'get_weekly_subscribers', lambda: fake_subs)
    monkeypatch.setattr(news_engine, '_send_admin_email', lambda *a, **k: True)

    captured = {}

    def _fake_send(title, analysis, doc_url, report_type='weekly', receivers=None):
        captured['receivers'] = receivers

    fake_module = types.SimpleNamespace(send_trend_report_email=_fake_send)
    monkeypatch.setitem(sys.modules, 'trend_analyzer', fake_module)

    state = _base_state()
    auto_intel_report.node_send_report(state)

    assert captured['receivers'] == fake_subs
    assert state['email_sent'] is True


def test_send_report_alerts_admin_when_subscriber_list_collapses(monkeypatch):
    """구독자 목록이 비정상적으로 작으면(관리자 1인 폴백) 운영 알림이 발송돼야 한다."""
    monkeypatch.setattr(auto_intel_report, 'get_weekly_subscribers', lambda: ['ironage73@gmail.com'])

    alerts = []
    monkeypatch.setattr(news_engine, '_send_admin_email',
                         lambda subject, body: alerts.append(subject) or True)

    fake_module = types.SimpleNamespace(send_trend_report_email=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, 'trend_analyzer', fake_module)

    state = _base_state()
    auto_intel_report.node_send_report(state)

    assert any('수신자' in a for a in alerts)


def test_send_report_no_alert_when_subscriber_list_healthy(monkeypatch):
    fake_subs = [f"user{i}@tta.or.kr" for i in range(45)]
    monkeypatch.setattr(auto_intel_report, 'get_weekly_subscribers', lambda: fake_subs)

    alerts = []
    monkeypatch.setattr(news_engine, '_send_admin_email',
                         lambda subject, body: alerts.append(subject) or True)

    fake_module = types.SimpleNamespace(send_trend_report_email=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, 'trend_analyzer', fake_module)

    state = _base_state()
    auto_intel_report.node_send_report(state)

    assert alerts == []
