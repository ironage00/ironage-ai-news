"""Check Gmail SMTP without sending a message or printing credentials."""

import os
import smtplib
import ssl
import sys
import re


def diagnose(sender, password, smtp_factory=smtplib.SMTP):
    if not sender or not password:
        print('Credentials: missing')
        return False
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
                    raise

            server.auth = traced_auth
            server.login(sender, password)
            print('Authentication: OK')
        return True
    except Exception as exc:
        print(f'{stage}: FAILED ({type(exc).__name__})')
        if isinstance(exc, smtplib.SMTPResponseException):
            print(f'SMTP response code: {exc.smtp_code}')
            raw = exc.smtp_error
            message = raw.decode('ascii', errors='ignore') if isinstance(raw, bytes) else str(raw)
            match = re.search(r'\b[245]\.[0-9]{1,3}\.[0-9]{1,3}\b', message)
            if match:
                print(f'Enhanced status code: {match.group()}')
        return False


if __name__ == '__main__':
    sys.exit(0 if diagnose(os.getenv('GMAIL_SENDER'), os.getenv('GMAIL_PASSWORD')) else 1)
