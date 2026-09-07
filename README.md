# CareerPearls v2

A production-quality **Job Board + Application Tracking System (ATS)** built with Flask.

## Tech Stack

- **Backend:** Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Migrate, Flask-Mail, Authlib
- **Database:** SQLite (switch to PostgreSQL via `DATABASE_URL` in `.env`)
- **Frontend:** Bootstrap 5 dark theme, Chart.js, animated auth UI
- **Auth:** Email/password, Google OAuth, GitHub OAuth, password reset via email

## Quick Start

### 1. Clone and set up environment

```bash
cd CareerPearls
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example file and fill in your values:

```bash
copy .env.example .env   # Windows
cp .env.example .env     # macOS/Linux
```

Edit `.env` with your settings. At minimum, change `SECRET_KEY`. For OAuth and email, add:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | Password reset & welcome emails |

**Google OAuth setup:** Create credentials at [Google Cloud Console](https://console.cloud.google.com/) → OAuth 2.0 → redirect URI: `http://127.0.0.1:5000/auth/google/callback`

**GitHub OAuth setup:** [GitHub Developer Settings](https://github.com/settings/developers) → New OAuth App → callback: `http://127.0.0.1:5000/auth/github/callback`

### 3. Run the app

```bash
python run.py
```

Open **http://127.0.0.1:5000**

**Default admin:** `admin@careerpearls.com` / `admin123`

### 4. Database migrations (optional)

```bash
set FLASK_APP=run.py
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
careerpearls/
├── app/
│   ├── models.py          # ALL database models (single file)
│   ├── auth/              # Login, register, OAuth, password reset
│   ├── candidate/         # Candidate dashboard, profile
│   ├── employer/          # Job posting, applications
│   ├── jobboard/          # Public job listings
│   ├── admin/             # Platform administration
│   ├── api/               # JSON REST endpoints
│   └── templates/         # Base layout + email templates
├── .env                   # Local secrets (git-ignored)
├── .env.example           # Safe template for repo
├── config.py
├── run.py
└── requirements.txt
```

## Features

- Role-based access (Candidate, Employer, Admin)
- Job posting, search, filter, apply with duplicate prevention
- Application status pipeline with history logging
- Google & GitHub OAuth with one-time role onboarding
- Password reset via email
- Employer/Candidate/Admin dashboards with Chart.js KPIs
- REST API at `/api/jobs`, `/api/applications`, etc.

## License

MIT
