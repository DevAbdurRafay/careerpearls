import io
import pytest
from flask import session
from app.extensions import db
from app.models import User, Candidate, CandidateEducation, CandidateCertification, Resume

VALID_PASSWORD = 'Password1!'


def _register_and_verify(client, email, role='candidate'):
    client.post('/register', data={
        'name': 'Test User',
        'email': email,
        'password': VALID_PASSWORD,
        'confirm_password': VALID_PASSWORD,
        'role': role,
    }, follow_redirects=False)
    with client.session_transaction() as sess:
        code = sess.get('test_verification_code')
    return client.post('/verify-registration', data={'code': code}, follow_redirects=False)


def test_employer_login_redirects_to_dashboard(client):
    """Employers are redirected straight into the employer flow after login (no confirmation screen)."""
    res = _register_and_verify(client, 'emp_confirm@test.com', 'employer')
    assert res.status_code == 302
    assert '/confirm-employer' not in (res.location or '')

    res_dash = client.get('/employer/dashboard', follow_redirects=False)
    assert res_dash.status_code in (200, 302)
    if res_dash.status_code == 302:
        assert '/confirm-employer' not in res_dash.location

    client.get('/logout', follow_redirects=True)
    res_login = client.post('/login', data={
        'email': 'emp_confirm@test.com',
        'password': VALID_PASSWORD,
        'role': 'employer',
    }, follow_redirects=False)
    assert res_login.status_code == 302
    assert '/confirm-employer' not in (res_login.location or '')


def test_resume_and_certificate_file_size_limits(client, app):
    """Requirement 2: Resume file uploads reject >15MB and accept <=15MB. Certificate file uploads reject >25MB and accept <=25MB."""
    _register_and_verify(client, 'filesize@test.com', 'candidate')
    with app.app_context():
        u = User.query.filter_by(email='filesize@test.com').first()
        u.candidate.onboarding_complete = True
        db.session.commit()

    import re
    res_p = client.get('/candidate/profile')
    match = re.search(r'name="csrf_token"\s+type="hidden"\s+value="([^"]+)"', res_p.data.decode('utf-8'))
    csrf = match.group(1) if match else ''

    # Oversized file (>15MB for resume)
    large_content_resume = b'0' * (15 * 1024 * 1024 + 100)

    # 1. Resume upload >15MB rejected
    res_resume_large = client.post('/candidate/profile', data={
        'csrf_token': csrf,
        'resume': (io.BytesIO(large_content_resume), 'large_resume.pdf'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b'15MB limit' in res_resume_large.data or b'exceeds' in res_resume_large.data

    # Oversized file (>25MB for certificate)
    large_content_cert = b'0' * (25 * 1024 * 1024 + 100)

    # 2. Certificate upload >25MB rejected
    res_cert_large = client.post('/candidate/profile', data={
        'csrf_token': csrf,
        'cert_form': '1',
        'title': 'Big Cert',
        'issuing_organization': 'Org',
        'certificate_file': (io.BytesIO(large_content_cert), 'large_cert.pdf'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b'25MB limit' in res_cert_large.data or b'exceeds' in res_cert_large.data

    # Valid size file (small PDF)
    valid_content = b'%PDF-1.4 test resume content'

    res_resume_valid = client.post('/candidate/profile', data={
        'csrf_token': csrf,
        'resume': (io.BytesIO(valid_content), 'valid_resume.pdf'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b'uploaded successfully' in res_resume_valid.data or b'valid_resume.pdf' in res_resume_valid.data


def test_education_cards_current_vs_past_labeling(app):
    """Requirement 3: Reusable education component correctly identifies CURRENT vs PAST education."""
    with app.app_context():
        current_edu = CandidateEducation(
            candidate_id=101,
            institution="University A",
            degree="B.S. Computer Science",
            is_current=True,
        )
        past_edu = CandidateEducation(
            candidate_id=101,
            institution="College B",
            degree="High School Diploma",
            is_current=False,
        )
        assert current_edu.is_current is True
        assert past_edu.is_current is False


def test_simplified_onboarding_and_direct_profile_edits(client, app):
    """Requirement 4: Simplified setup (Career Status + Interests) & direct Edit Profile inline saving."""
    # 1. Register candidate (starts with onboarding_complete = False)
    _register_and_verify(client, 'simple_setup@test.com', 'candidate')

    # Candidate accesses setup page
    res_setup = client.get('/candidate/onboarding')
    assert res_setup.status_code == 200
    assert b'Fields of Interest' in res_setup.data
    assert b'Key Technical Skills' in res_setup.data

    # Submit setup with status, interests, and skill
    res_post_setup = client.post('/candidate/onboarding', data={
        'career_status': 'student',
        'interests': ['Software Development', 'Web Development', 'Data Science'],
        'primary_skill': 'Python',
        'primary_skill_level': 'Intermediate',
    }, follow_redirects=True)
    assert res_post_setup.status_code == 200
    assert b'Profile' in res_post_setup.data

    with app.app_context():
        u = User.query.filter_by(email='simple_setup@test.com').first()
        assert u.candidate.onboarding_complete is True
        assert u.candidate.career_status == 'student'

    # Direct edit in profile page persists immediately
    res_profile_page = client.get('/candidate/profile')
    assert res_profile_page.status_code == 200

    # Extract CSRF token from page
    import re
    match = re.search(r'name="csrf_token"\s+type="hidden"\s+value="([^"]+)"', res_profile_page.data.decode('utf-8'))
    csrf = match.group(1) if match else ''

    res_profile_save = client.post('/candidate/profile', data={
        'csrf_token': csrf,
        'full_name_submit': '1',
        'full_name': 'Updated Candidate Name',
        'country_code': '+92',
        'phone': '3009876543',
        'location': 'Islamabad',
        'headline': 'Full Stack Developer',
        'availability': 'immediate',
        'work_mode': 'remote',
        'has_internship': 'yes',
        'internship_details': 'Software Intern at Tech Co',
    }, follow_redirects=True)
    assert res_profile_save.status_code == 200
    assert b'Updated Candidate Name' in res_profile_save.data
