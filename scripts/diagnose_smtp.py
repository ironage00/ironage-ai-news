"""Check Gmail SMTP without sending a message or printing credentials."""

import os
import smtplib
import ssl
import sys
import re


def describe_credentials(sender, password):
    """값은 찍지 않고 모양만 알린다 — 535의 흔한 원인(공백·줄바꿈 포함, 일반 비밀번호 입력, 계정 불일치)을 가리기 위함."""
    compact = re.sub(r'\s+', '', password)
    lines = [
        f'Password length: {len(password)} (without whitespace: {len(compact)})',
        'Password whitespace: ' + ('none' if compact == password else
                                   'leading/trailing' if password.strip() == compact else 'inside'),
        'Password looks like a Google app password (16 lowercase letters): '
        + ('yes' if re.fullmatch(r'[a-z]{16}', compact) else 'NO'),
        'Sender whitespace: ' + ('none' if sender == sender.strip() else 'leading/trailing'),
    ]
    domain = sender.strip().rpartition('@')[2].lower() if '@' in sender else ''
    lines.append('Sender domain: ' + ('missing @' if not domain else
                                      'gmail.com' if domain in ('gmail.com', 'googlemail.com') else
                                      'custom domain (Google Workspace account)'))
    return lines


def _enhanced(exc):
    raw = exc.smtp_error
    message = raw.decode('ascii', errors='ignore') if isinstance(raw, bytes) else str(raw)
    match = re.search(r'\b[245]\.[0-9]{1,3}\.[0-9]{1,3}\b', message)
    return match.group() if match else ''


def diagnose(sender, password, smtp_factory=smtplib.SMTP):
    if not sender or not password:
        print('Credentials: missing')
        return False
    for line in describe_credentials(sender, password):
        print(line)
    stage = 'connection'
    try:
        with smtp_factory('smtp.gmail.com', 587, timeout=20) as server:
            print('Connection: OK')
            stage = 'EHLO'
            if server.ehlo()[0] != 250:
                raise RuntimeError('EHLO rejected')
            stage = 'STARTTLS'
            server.starttls(context=ssl.create_default_context())
            print('STARTTLS: OK')
            stage = 'EHLO after TLS'
            if server.ehlo()[0] != 250:
                raise RuntimeError('EHLO rejected after TLS')
            stage = 'authentication'
            mechanisms = server.esmtp_features.get('auth', '').upper().split()
            print('Advertised AUTH methods: ' + (', '.join(m for m in mechanisms if m in {'PLAIN', 'LOGIN', 'XOAUTH2'}) or 'none recognized'))
            original_auth = server.auth

            def traced_auth(mechanism, *args, **kwargs):
                print('AUTH attempt: ' + (mechanism if mechanism in {'PLAIN', 'LOGIN'} else 'other'))
                try:
                    return original_auth(mechanism, *args, **kwargs)
                except smtplib.SMTPResponseException as exc:
                    print(f'AUTH response code: {exc.smtp_code}')
                    if _enhanced(exc):
                        print(f'AUTH enhanced status code: {_enhanced(exc)}')
                    raise

            server.auth = traced_auth
            server.login(sender, password)
            print('Authentication: OK')
        return True
    except Exception as exc:
        print(f'{stage}: FAILED ({type(exc).__name__})')
        if isinstance(exc, smtplib.SMTPResponseException):
            print(f'SMTP response code: {exc.smtp_code}')
            if _enhanced(exc):
                print(f'Enhanced status code: {_enhanced(exc)}')
        return False


def diagnose_with_retry(sender, password, smtp_factory=smtplib.SMTP):
    # 등록된 값 그대로 먼저 시도하고, 실패했고 공백이 섞여 있으면 공백을 뺀 값으로 한 번 더 시도한다.
    # (구글은 앱 비밀번호를 'abcd efgh ijkl mnop'처럼 띄어 보여 준다.) 반환값은 '등록된 값 그대로'의 성공 여부.
    if diagnose(sender, password, smtp_factory):
        return True
    compact = re.sub(r'\s+', '', password or '')
    if sender and compact and compact != password:
        print('--- Retry with whitespace removed from the password ---')
        ok = diagnose(sender.strip(), compact, smtp_factory)
        print('Retry without whitespace: ' + ('OK - whitespace was the problem' if ok else 'FAILED - whitespace is not the cause'))
    return False


if __name__ == '__main__':
    sys.exit(0 if diagnose_with_retry(os.getenv('GMAIL_SENDER'), os.getenv('GMAIL_PASSWORD')) else 1)
