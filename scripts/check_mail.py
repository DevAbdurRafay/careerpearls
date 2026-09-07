"""Test Gmail SMTP from .env — run: python scripts/check_mail.py"""
import os
import smtplib
import ssl
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, '.env'))


def clean(value):
    if not value:
        return None
    value = value.strip().strip('"').strip("'")
    if value:
        value = value.replace(' ', '')
        value = ''.join(ch for ch in value if ch.isascii() and not ch.isspace())
    return value or None


def main():
    username = clean(os.getenv('MAIL_USERNAME'))
    password = clean(os.getenv('MAIL_PASSWORD'))
    server = os.getenv('MAIL_SERVER', 'smtp.gmail.com').strip()

    print('CareerPearls — Gmail SMTP check\n')
    if not username or not password:
        print('FAIL: MAIL_USERNAME or MAIL_PASSWORD missing in .env')
        sys.exit(1)

    print(f'  Username: {username}')
    print(f'  Password: {"*" * len(password)} ({len(password)} chars)')
    if len(password) != 16:
        print('  WARN: Gmail App Password should be exactly 16 characters.')
    print()

    context = ssl.create_default_context()
    attempts = [
        ('STARTTLS', 587, 'starttls'),
        ('SSL', 465, 'ssl'),
    ]

    for label, port, mode in attempts:
        print(f'Trying {label} on {server}:{port} ... ', end='', flush=True)
        try:
            if mode == 'ssl':
                with smtplib.SMTP_SSL(server, port, context=context, timeout=30) as smtp:
                    smtp.login(username, password)
            else:
                with smtplib.SMTP(server, port, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    smtp.login(username, password)
            print('OK — login accepted.')
            print('\nSMTP works. Restart Flask and try registration again.')
            sys.exit(0)
        except smtplib.SMTPAuthenticationError as exc:
            print('FAIL — Bad credentials (535).')
            print(f'  Detail: {exc}')
        except Exception as exc:
            print(f'FAIL — {type(exc).__name__}: {exc}')

    print('\nBoth ports failed. Do this:')
    print('  1. https://myaccount.google.com/apppasswords — delete old, create NEW App Password')
    print('  2. MAIL_USERNAME must match the Gmail account that owns the App Password')
    print('  3. Update .env (no quotes), restart server')
    print('  4. https://accounts.google.com/DisplayUnlockCaptcha — unlock, then re-run this script')
    sys.exit(1)


if __name__ == '__main__':
    main()
