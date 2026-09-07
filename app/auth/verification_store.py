"""Temporary session-based email verification (DB table later)."""

from datetime import datetime

from flask import session, current_app

from app.email_utils import (
    generate_verification_code,
    hash_verification_code,
    check_verification_code,
    verification_expires_at,
)

SESSION_KEY = 'pending_registration'


def _parse_expires(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def get_pending_registration():
    data = session.get(SESSION_KEY)
    if not data:
        return None
    expires_at = _parse_expires(data.get('expires_at'))
    if not expires_at:
        return None
    return {
        'name': data.get('name', ''),
        'email': data.get('email', '').lower(),
        'password_hash': data.get('password_hash', ''),
        'role': data.get('role', 'candidate'),
        'code_hash': data.get('code_hash', ''),
        'expires_at': expires_at,
    }


def save_pending_registration(name, email, password_hash, role, code):
    expires_at = verification_expires_at()
    session[SESSION_KEY] = {
        'name': name.strip(),
        'email': email.lower(),
        'password_hash': password_hash,
        'role': role,
        'code_hash': hash_verification_code(code),
        'expires_at': expires_at.isoformat(),
    }
    session['pending_verification_email'] = email.lower()
    if current_app.config.get('TESTING'):
        session['test_verification_code'] = code
    return expires_at


def update_verification_code(code):
    pending = session.get(SESSION_KEY)
    if not pending:
        return None
    expires_at = verification_expires_at()
    pending['code_hash'] = hash_verification_code(code)
    pending['expires_at'] = expires_at.isoformat()
    session[SESSION_KEY] = pending
    if current_app.config.get('TESTING'):
        session['test_verification_code'] = code
    return expires_at


def clear_pending_registration():
    session.pop(SESSION_KEY, None)
    session.pop('pending_verification_email', None)
    session.pop('test_verification_code', None)


def is_pending_expired(pending):
    return datetime.utcnow() > pending['expires_at']


def verify_submitted_code(pending, code):
    return check_verification_code(pending['code_hash'], code)


def create_registration_code():
    return generate_verification_code()


RESET_SESSION_KEY = 'pending_password_reset'


def get_pending_password_reset():
    data = session.get(RESET_SESSION_KEY)
    if not data:
        return None
    expires_at = _parse_expires(data.get('expires_at'))
    if not expires_at:
        return None
    return {
        'email': data.get('email', '').lower(),
        'code_hash': data.get('code_hash', ''),
        'expires_at': expires_at,
        'verified': data.get('verified', False),
    }


def save_pending_password_reset(email, code):
    expires_at = verification_expires_at()
    session[RESET_SESSION_KEY] = {
        'email': email.lower(),
        'code_hash': hash_verification_code(code),
        'expires_at': expires_at.isoformat(),
        'verified': False,
    }
    if current_app.config.get('TESTING'):
        session['test_reset_code'] = code
    return expires_at


def update_password_reset_code(code):
    pending = session.get(RESET_SESSION_KEY)
    if not pending:
        return None
    expires_at = verification_expires_at()
    pending['code_hash'] = hash_verification_code(code)
    pending['expires_at'] = expires_at.isoformat()
    pending['verified'] = False
    session[RESET_SESSION_KEY] = pending
    if current_app.config.get('TESTING'):
        session['test_reset_code'] = code
    return expires_at


def mark_password_reset_verified():
    pending = session.get(RESET_SESSION_KEY)
    if pending:
        pending['verified'] = True
        session[RESET_SESSION_KEY] = pending


def clear_pending_password_reset():
    session.pop(RESET_SESSION_KEY, None)
    session.pop('test_reset_code', None)

