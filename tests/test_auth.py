import pytest
from flask import session
from app.extensions import db
from app.models import User

VALID_PASSWORD = 'Password1!'


def _register_and_verify(client, email, role='candidate', password=VALID_PASSWORD):
    client.post('/register', data={
        'name': 'Test User',
        'email': email,
        'password': password,
        'confirm_password': password,
        'role': role,
    }, follow_redirects=False)
    with client.session_transaction() as sess:
        code = sess.get('test_verification_code')
    assert code is not None
    return client.post('/verify-registration', data={'code': code}, follow_redirects=True)




def test_register_candidate(client):
    response = _register_and_verify(client, 'candidate@test.com', 'candidate')
    assert response.status_code == 200
    user = User.query.filter_by(email='candidate@test.com').first()
    assert user is not None
    assert user.role == 'candidate'
    assert user.candidate is not None


def test_register_employer(client):
    response = _register_and_verify(client, 'employer@test.com', 'employer')
    assert response.status_code == 200
    user = User.query.filter_by(email='employer@test.com').first()
    assert user is not None
    assert user.role == 'employer'
    assert user.recruiter is not None


def test_verify_invalid_code(client):
    client.post('/register', data={
        'name': 'Bad Code User',
        'email': 'badcode@test.com',
        'password': VALID_PASSWORD,
        'confirm_password': VALID_PASSWORD,
        'role': 'candidate',
    }, follow_redirects=False)
    response = client.post('/verify-registration', data={'code': '000000'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid verification code' in response.data
    assert User.query.filter_by(email='badcode@test.com').first() is None


def test_register_weak_password(client):
    response = client.post('/register', data={
        'name': 'Weak Pass User',
        'email': 'weak@test.com',
        'password': 'password',
        'confirm_password': 'password',
        'role': 'candidate',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Password must include' in response.data
    assert User.query.filter_by(email='weak@test.com').first() is None


def test_register_password_mismatch(client):
    response = client.post('/register', data={
        'name': 'Mismatch User',
        'email': 'mismatch@test.com',
        'password': VALID_PASSWORD,
        'confirm_password': 'Password2!',
        'role': 'candidate',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Passwords do not match' in response.data
    assert User.query.filter_by(email='mismatch@test.com').first() is None


def test_login(client):
    _register_and_verify(client, 'login@test.com', 'candidate')
    client.get('/logout', follow_redirects=True)
    response = client.post('/login', data={
        'email': 'login@test.com',
        'password': VALID_PASSWORD,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Profile' in response.data or b'CareerPearls' in response.data or b'Logout' in response.data


def test_forgot_password_and_reset_flow(client, app):
    _register_and_verify(client, 'resetme@test.com', 'candidate')
    with app.app_context():
        u = User.query.filter_by(email='resetme@test.com').first()
        u.candidate.onboarding_complete = True
        db.session.commit()
    client.get('/logout', follow_redirects=True)

    # 1. Request forgot password
    resp = client.post('/forgot-password', data={'email': 'resetme@test.com'}, follow_redirects=False)
    assert resp.status_code == 302
    assert '/forgot-password/verify' in resp.location

    # Check reset code was saved in session during testing
    with client.session_transaction() as sess:
        reset_code = sess.get('test_reset_code')
    assert reset_code is not None
    assert len(reset_code) == 6

    # 2. Verify invalid code fails
    resp_invalid = client.post('/forgot-password/verify', data={'code': '999999'}, follow_redirects=True)
    assert b'Invalid verification code' in resp_invalid.data

    # 3. Verify valid code succeeds
    resp_verify = client.post('/forgot-password/verify', data={'code': reset_code}, follow_redirects=False)
    assert resp_verify.status_code == 302
    assert '/reset-password' in resp_verify.location

    # 4. Set new password and confirm
    NEW_PASS = 'NewSecret1!'
    resp_reset = client.post('/reset-password', data={
        'password': NEW_PASS,
        'confirm_password': NEW_PASS,
    }, follow_redirects=True)
    assert resp_reset.status_code == 200
    assert b'Password updated' in resp_reset.data

    # 5. Verify user can now log in with new password
    resp_login = client.post('/login', data={
        'email': 'resetme@test.com',
        'password': NEW_PASS,
    }, follow_redirects=True)
    assert resp_login.status_code == 200
    assert b'Incorrect password' not in resp_login.data



def test_login_unregistered_email(client):
    response = client.post('/login', data={
        'email': 'nobody@test.com',
        'password': 'wrongpassword',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'not registered' in response.data


def test_login_wrong_password(client, app):
    _register_and_verify(client, 'wrongpass@test.com', 'candidate')
    with app.app_context():
        u = User.query.filter_by(email='wrongpass@test.com').first()
        u.candidate.onboarding_complete = True
        db.session.commit()
    client.get('/logout', follow_redirects=True)
    response = client.post('/login', data={
        'email': 'wrongpass@test.com',
        'password': 'WrongPass1!',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Incorrect password' in response.data


def test_duplicate_application_prevention(app, client):
    from datetime import datetime, timedelta
    from app.models import Candidate, Company, Recruiter, Job, JobCategory, Resume
    from app.models import can_apply

    with app.app_context():
        cat = JobCategory(name='Test')
        db.session.add(cat)
        db.session.flush()

        company = Company(name='Test Co')
        db.session.add(company)
        db.session.flush()

        emp = User(name='Emp', email='emp@test.com', role='employer')
        emp.set_password('pass')
        db.session.add(emp)
        db.session.flush()

        recruiter = Recruiter(user_id=emp.id, company_id=company.id)
        db.session.add(recruiter)
        db.session.flush()

        job = Job(
            company_id=company.id, title='Dev', category_id=cat.id,
            description='Test', posted_by=recruiter.id,
            closes_at=datetime.utcnow() + timedelta(days=30),
        )
        db.session.add(job)
        db.session.flush()

        user = User(name='Cand', email='cand@test.com', role='candidate')
        user.set_password('pass')
        db.session.add(user)
        db.session.flush()

        candidate = Candidate(user_id=user.id, full_name='Cand')
        db.session.add(candidate)
        db.session.flush()

        resume = Resume(candidate_id=candidate.id, file_path='test.pdf')
        db.session.add(resume)
        db.session.commit()

        allowed, _ = can_apply(candidate.id, job)
        assert allowed is True

        from app.models import Application
        app_obj = Application(job_id=job.id, candidate_id=candidate.id, resume_id=resume.id, status='Applied')
        db.session.add(app_obj)
        db.session.commit()

        allowed, msg = can_apply(candidate.id, job)
        assert allowed is False
        assert 'already applied' in msg.lower()
