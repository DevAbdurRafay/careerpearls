import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import db
from app.utils import get_or_create_user

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').strip().lower()
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '').strip()

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    print('ERROR: Set ADMIN_EMAIL and ADMIN_PASSWORD in your .env file first.')
    print('Example:')
    print('  ADMIN_EMAIL=you@gmail.com')
    print('  ADMIN_PASSWORD=YourSecurePassword123!')
    sys.exit(1)

app = create_app()
with app.app_context():
    user, _created = get_or_create_user(
        ADMIN_EMAIL,
        defaults={'name': 'Administrator', 'role': 'admin', 'approval_status': 'approved'},
        update={'role': 'admin', 'approval_status': 'approved'},
    )
    user.set_password(ADMIN_PASSWORD)
    db.session.commit()
    admin_path = app.config['ADMIN_PATH']
    print('Admin account configured successfully!')
    print(f'Email: {ADMIN_EMAIL}')
    print(f'Admin panel: http://localhost:5000/{admin_path}/')
