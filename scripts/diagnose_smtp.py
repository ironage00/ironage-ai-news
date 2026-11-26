"""Check Gmail SMTP without sending a message or printing credentials."""

import os
import smtplib
import ssl
import sys


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
            server.login(sender, password)
            print('Authentication: OK')
        return True
    except Exception as exc:
        print(f'{stage}: FAILED ({type(exc).__name__})')
        return False


if __name__ == '__main__':
    sys.exit(0 if diagnose(os.getenv('GMAIL_SENDER'), os.getenv('GMAIL_PASSWORD')) else 1)
