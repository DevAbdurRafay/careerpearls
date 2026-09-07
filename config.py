import os
import sys # Allow program to get infromation from system and python interpreter
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


def _clean_env(value):
    if value is None:
        return None
    value = str(value).strip().strip('"').strip("'")
    return value or None


def _clean_mail_password(value):
    """Gmail app passwords are 16 chars; users often paste with spaces."""
    cleaned = _clean_env(value)
    if cleaned:
        cleaned = cleaned.replace(' ', '')
        cleaned = ''.join(ch for ch in cleaned if ch.isascii() and not ch.isspace())
    return cleaned


_REQUIRED_ENV_VARS = [
    'FLASK_SECRET_KEY',
    'GOOGLE_CLIENT_ID',
    'GOOGLE_CLIENT_SECRET',
    'APP_BASE_URL',
]


def check_required_env_vars():
    """Print clear errors for missing required env vars; returns list of missing names."""
    missing = [var for var in _REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        print('\n[CareerPearls] ❌  Missing required environment variables:', file=sys.stderr)
        for var in missing:
            print(f'  • {var}  ← add this to your .env file', file=sys.stderr)
        print('\nOAuth will not work until these are set.\n', file=sys.stderr)
    return missing


class Config:
    
    SECRET_KEY = (
        os.environ.get('FLASK_SECRET_KEY')
        or os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    )

    _db_url = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(basedir, 'careerpearls.db'),
    )
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    elif _db_url.startswith('sqlite:///') and not _db_url.startswith('sqlite:////'):
        _db_path = _db_url.replace('sqlite:///', '', 1)
        if not os.path.isabs(_db_path):
            _db_path = os.path.join(basedir, _db_path)
        _db_url = 'sqlite:///' + _db_path.replace('\\', '/')
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    if 'postgresql' in _db_url:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 10,
            'max_overflow': 20,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'sslmode': 'require',
            },
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
        }

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(basedir, 'uploads'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 52428800))  # 50MB to handle certificate + resume uploads safely
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}

    MAIL_SERVER = _clean_env(os.environ.get('MAIL_SERVER', 'smtp.gmail.com'))
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')
    MAIL_USERNAME = _clean_env(os.environ.get('MAIL_USERNAME'))
    MAIL_PASSWORD = _clean_mail_password(os.environ.get('MAIL_PASSWORD'))
    MAIL_DEFAULT_SENDER = _clean_env(os.environ.get('MAIL_DEFAULT_SENDER')) or MAIL_USERNAME

    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000').rstrip('/')

    VERIFICATION_CODE_EXPIRY_MINUTES = int(os.environ.get('VERIFICATION_CODE_EXPIRY_MINUTES', 2))

    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
    GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')

    PERMANENT_SESSION_LIFETIME = 604800  # 7 days
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = False  # Set to True in production with HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    TESTING_MODE = os.environ.get('TESTING_MODE', 'False').lower() in ('true', '1', 'yes')
    CERTIFICATE_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

    ADMIN_PATH = _clean_env(os.environ.get('ADMIN_PATH', 'portal-control-x99')) or 'portal-control-x99'
    ADMIN_EMAIL = _clean_env(os.environ.get('ADMIN_EMAIL'))
    ADMIN_PASSWORD = _clean_env(os.environ.get('ADMIN_PASSWORD'))
