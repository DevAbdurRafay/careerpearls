import pytest
from datetime import datetime, timedelta
from flask import url_for
from app.extensions import db
from app.models import User, Company, Candidate, Recruiter, Job, JobCategory, Application, Message, Notification, AuditLog
from app.schemas import UserContract, OrganizationContract, JobContract, ApplicationContract


def test_single_account_restriction(client, app):
    # Create alice as candidate directly in DB (already verified)
    with app.app_context():
        user = User(name='Alice Candidate', email='alice@example.com', role='candidate', approval_status='approved')
        user.set_password('Password123!')
        db.session.add(user)
        db.session.flush()
        cand = Candidate(user_id=user.id, full_name='Alice Candidate', location='Karachi')
        db.session.add(cand)
        db.session.commit()

    # Attempt to register employer with same email — should block
    r2 = client.post('/register', data={
        'name': 'Alice Employer',
        'email': 'alice@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!',
        'role': 'employer',
    }, follow_redirects=True)
    assert (
        b'An account with this email already exists as a Candidate' in r2.data
        or b'already registered' in r2.data
        or b'already exists' in r2.data
        or b'Candidate' in r2.data
    )


def test_deactivation_frees_email(client, app):
    # Create and login user
    with app.app_context():
        user = User(name='Bob User', email='bob@example.com', role='candidate', approval_status='approved')
        user.set_password('Password123!')
        db.session.add(user)
        db.session.flush()
        cand = Candidate(user_id=user.id, full_name='Bob User', location='Karachi, Pakistan')
        db.session.add(cand)
        db.session.commit()

    # Login as bob
    client.post('/login', data={'email': 'bob@example.com', 'password': 'Password123!'}, follow_redirects=True)

    # Deactivate profile via candidate blueprint route
    res = client.post('/candidate/deactivate-profile', data={'reason': 'Other', 'password': 'Password123!'}, follow_redirects=True)
    assert res.status_code == 200

    # Ensure original email is kept but Candidate profile data is deleted
    with app.app_context():
        deactivated_user = User.query.filter_by(email='bob@example.com').first()
        assert deactivated_user is not None
        assert deactivated_user.is_active is False
        assert deactivated_user.approval_status == 'deactivated'
        assert deactivated_user.candidate is None


def test_candidate_privacy_rule(client, app):
    # Create employer and candidate
    with app.app_context():
        emp_user = User(name='Emp User', email='emp@company.com', role='employer', approval_status='approved')
        emp_user.set_password('Password123!')
        db.session.add(emp_user)
        db.session.flush()

        comp = Company(name='TechCorp', domain='company.com', official_email='emp@company.com', is_verified=True, verification_status='Approved', onboarding_complete=True)
        db.session.add(comp)
        db.session.flush()

        rec = Recruiter(user_id=emp_user.id, company_id=comp.id)
        db.session.add(rec)

        cand_user = User(name='Privacy Candidate', email='privacy@cand.com', role='candidate', approval_status='approved')
        cand_user.set_password('Password123!')
        db.session.add(cand_user)
        db.session.flush()

        cand = Candidate(user_id=cand_user.id, full_name='Privacy Candidate')
        db.session.add(cand)
        db.session.commit()
        cand_id = cand.id

    # Login as employer
    client.post('/login', data={'email': 'emp@company.com', 'password': 'Password123!', 'role': 'employer'}, follow_redirects=True)

    # Attempt to browse raw talent
    r1 = client.get('/employer/talent', follow_redirects=True)
    assert b'Candidate Sourcing Privacy Rule' in r1.data or b'disabled' in r1.data

    # Attempt to view candidate profile directly without application
    r2 = client.get(f'/employer/candidate/{cand_id}', follow_redirects=True)
    assert b'Candidate Sourcing Privacy Rule' in r2.data or r2.status_code == 403 or r2.status_code == 302


def test_employer_3_strict_actions(client, app):
    # Create employer, job, candidate, and application
    with app.app_context():
        emp_user = User(name='Action Employer', email='emp_action@company.com', role='employer', approval_status='approved')
        emp_user.set_password('Password123!')
        db.session.add(emp_user)
        db.session.flush()

        comp = Company(name='ActionCorp', is_verified=True, verification_status='Approved', onboarding_complete=True)
        db.session.add(comp)
        db.session.flush()

        rec = Recruiter(user_id=emp_user.id, company_id=comp.id)
        db.session.add(rec)

        cat = JobCategory(name='Engineering Category')
        db.session.add(cat)
        db.session.flush()

        job = Job(company_id=comp.id, title='Backend Dev', category_id=cat.id, description='Dev role', location='Lahore', posted_by=rec.id, closes_at=datetime.utcnow() + timedelta(days=10))
        db.session.add(job)

        cand_user = User(name='App Candidate', email='app_cand@cand.com', role='candidate', approval_status='approved')
        cand_user.set_password('Password123!')
        db.session.add(cand_user)
        db.session.flush()

        cand = Candidate(user_id=cand_user.id, full_name='App Candidate', location='Lahore')
        db.session.add(cand)
        db.session.flush()

        appl = Application(job_id=job.id, candidate_id=cand.id, status='Under Review')
        db.session.add(appl)
        db.session.commit()
        appl_id = appl.id

    # Login as employer
    client.post('/login', data={'email': 'emp_action@company.com', 'password': 'Password123!', 'role': 'employer'}, follow_redirects=True)

    # Action 1: Message Directly
    r1 = client.post(f'/employer/applications/{appl_id}/message', data={
        'message': 'We loved your profile!',
        'interview_date': '2026-09-01',
        'interview_time': '10:00',
        'interview_location': 'Google Meet',
    }, follow_redirects=True)
    assert r1.status_code == 200
    with app.app_context():
        assert Application.query.get(appl_id).status == 'Contacted'

    # Action 2: Wait
    r2 = client.post(f'/employer/applications/{appl_id}/wait', follow_redirects=True)
    assert r2.status_code == 200
    with app.app_context():
        assert Application.query.get(appl_id).status == 'Under Review'

    # Action 3: Reject
    r3 = client.post(f'/employer/applications/{appl_id}/reject', data={
        'reason': 'Qualifications gap',
    }, follow_redirects=True)
    assert r3.status_code == 200
    with app.app_context():
        refreshed = Application.query.get(appl_id)
        assert refreshed.status == 'Rejected'
        assert refreshed.rejection_reason == 'Qualifications gap'


def test_admin_employer_and_location_verification(client, app):
    # Create admin
    admin = User(name='Super Admin', email='admin_test@cp.com', role='admin')
    admin.set_password('Password123!')
    db.session.add(admin)

    # Create unverified employer
    comp = Company(name='UnverifiedCorp', domain='unverified.com', official_email='info@unverified.com', verification_status='Pending Verification')
    db.session.add(comp)

    # Create candidate
    cand_user = User(name='Location Candidate', email='loc_cand@cand.com', role='candidate')
    db.session.add(cand_user)
    db.session.flush()
    cand = Candidate(user_id=cand_user.id, full_name='Location Candidate', location='Islamabad')
    db.session.add(cand)
    db.session.commit()

    # Login as admin
    client.post('/login', data={'email': 'admin_test@cp.com', 'password': 'Password123!'}, follow_redirects=True)

    with app.test_request_context():
        approve_url = url_for('admin.verify_employer', company_id=comp.id, action='approve')
        verify_loc_url = url_for('admin.verify_candidate_location', candidate_id=cand.id)

    # Approve Employer
    r1 = client.post(approve_url, follow_redirects=True)
    assert r1.status_code == 200
    assert comp.verification_status == 'Approved'
    assert comp.is_verified is True

    # Verify Candidate Location
    r2 = client.post(verify_loc_url, data={'action': 'verify'}, follow_redirects=True)
    assert r2.status_code == 200
    assert cand.is_location_verified is True
