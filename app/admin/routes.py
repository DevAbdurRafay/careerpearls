import csv
import io
from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    jsonify, make_response, abort,
)
from flask_login import login_required, current_user, login_user
from sqlalchemy import func, or_, and_, desc
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import db
from app.models import (
    User, Job, Application, Complaint, AuditLog, JobCategory,
    Candidate, Recruiter, Company, Notification, create_audit_log,
)
from app.utils import admin_required, get_current_admin
from app.email_utils import send_complaint_status_update_email
from app.auth.forms import LoginForm
from app.candidate.onboarding_store import clear_onboarding_session

admin_bp = Blueprint('admin', __name__, template_folder='templates')


def _get_admin_id():
    """Safely get admin user ID without relying on Flask-Login current_user."""
    admin = get_current_admin()
    if admin and hasattr(admin, 'id') and admin.id:
        return admin.id
    if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated and hasattr(current_user, 'id'):
        return current_user.id
    from flask import session
    return session.get('admin_user_id')


@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    from flask import session, current_app
    admin = get_current_admin()
    if admin:
        return redirect(url_for('admin.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        email = (form.email.data or '').lower().strip()
        password_input = form.password.data or ''
        user = User.query.filter_by(email=email).first()

        env_admin_email = (current_app.config.get('ADMIN_EMAIL') or '').lower().strip()
        env_admin_pass = current_app.config.get('ADMIN_PASSWORD')

        if not user:
            if env_admin_email and email == env_admin_email:
                user = User(
                    name='Super Admin',
                    email=env_admin_email,
                    role='admin',
                    approval_status='approved',
                    is_active=True,
                )
                user.set_password(env_admin_pass or 'admin123')
                db.session.add(user)
                db.session.commit()
            else:
                flash('Invalid credentials. Admin account not found.', 'warning')
                return render_template('admin_login.html', form=form)

        if user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'danger')
            return render_template('admin_login.html', form=form)

        # Check password against DB hash or against configured .env ADMIN_PASSWORD
        is_valid_password = user.check_password(password_input)
        if not is_valid_password and env_admin_pass and password_input == env_admin_pass:
            # Sync DB password with the .env password
            user.set_password(password_input)
            db.session.commit()
            is_valid_password = True

        if is_valid_password:
            if not user.is_active:
                flash('Your account has been deactivated.', 'danger')
                return redirect(url_for('admin.admin_login'))
            # Dedicated Admin Session ID - keeps admin session separate from Flask-Login user session
            # allowing simultaneous multi-tab workflow between Admin and Employer/Candidate tabs!
            session['admin_user_id'] = user.id
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            flash('Welcome back, Super Admin.', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Incorrect password. Please try again.', 'danger')

    return render_template('admin_login.html', form=form)


@admin_bp.context_processor
def inject_admin_context():
    return {'admin_user': get_current_admin()}


@admin_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    from flask import session
    session.pop('admin_user_id', None)
    flash('Super Admin logged out successfully.', 'info')
    return redirect(url_for('admin.admin_login'))


admin_logout = logout


# ---------------------------------------------------------------------------
# Dashboard (Ultra-Fast Batch Queries)
# ---------------------------------------------------------------------------

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    # Only count real, non-deactivated active users
    user_counts = dict(
        db.session.query(User.role, func.count(User.id))
        .filter(User.approval_status != 'deactivated')
        .group_by(User.role)
        .all()
    )
    total_users = sum(user_counts.values())
    candidates = user_counts.get('candidate', 0)
    employers = user_counts.get('employer', 0)

    # Valid partner companies tied to real employers
    partner_companies = (
        Company.query.join(Recruiter, Company.id == Recruiter.company_id)
        .join(User, and_(Recruiter.user_id == User.id, User.approval_status != 'deactivated'))
        .filter(or_(Company.is_verified.is_(True), Company.verification_status == 'Approved'))
        .count()
    )
    active_jobs = Job.query.filter_by(status='active').count()
    
    # Complaint statistics by status
    complaint_counts = dict(
        db.session.query(Complaint.status, func.count(Complaint.id))
        .group_by(Complaint.status)
        .all()
    )
    pending_complaints = complaint_counts.get('Pending', 0) + complaint_counts.get('Open', 0) + complaint_counts.get(None, 0)
    in_review_complaints = complaint_counts.get('In Review', 0) + complaint_counts.get('Under Review', 0) + complaint_counts.get('In Progress', 0)
    resolved_complaints = complaint_counts.get('Resolved', 0)
    rejected_complaints = complaint_counts.get('Rejected', 0) + complaint_counts.get('Dismissed', 0)
    
    # Employer verification statistics
    pending_employers = (
        Company.query.join(Recruiter, Company.id == Recruiter.company_id)
        .join(User, and_(Recruiter.user_id == User.id, User.approval_status != 'deactivated'))
        .filter(or_(Company.verification_status == 'Pending Verification', Company.verification_status == 'pending', Company.verification_status.is_(None)))
        .count()
    )
    pending_verifications = pending_employers
    verified_employers = partner_companies
    rejected_employers = (
        Company.query.join(Recruiter, Company.id == Recruiter.company_id)
        .join(User, and_(Recruiter.user_id == User.id, User.approval_status != 'deactivated'))
        .filter(Company.verification_status == 'Rejected')
        .count()
    )
    
    pending_jobs = 0

    # Applications this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    applications_this_week = Application.query.filter(Application.applied_at >= week_ago).count()

    # Most recent valid employer
    recent_employer = (
        User.query.filter(User.role == 'employer', User.approval_status != 'deactivated')
        .order_by(User.created_at.desc())
        .first()
    )

    recent_logs = (
        AuditLog.query
        .options(joinedload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
        .limit(10).all()
    )

    # FAST SIGNUPS BATCH QUERY (Single SQL query instead of 30 queries!)
    thirty_days_ago = datetime.utcnow().date() - timedelta(days=30)
    signup_rows = (
        db.session.query(func.date(User.created_at).label('d'), func.count(User.id))
        .filter(User.created_at >= thirty_days_ago, User.approval_status != 'deactivated')
        .group_by(func.date(User.created_at))
        .all()
    )
    signup_map = {str(r[0]): r[1] for r in signup_rows}
    signup_labels, signup_counts = [], []
    for i in range(29, -1, -1):
        day_date = datetime.utcnow().date() - timedelta(days=i)
        signup_labels.append(day_date.strftime('%b %d'))
        signup_counts.append(signup_map.get(day_date.isoformat(), 0))

    # FAST APPLICATIONS BATCH QUERY (Single SQL query instead of 8 queries!)
    eight_weeks_ago = datetime.utcnow().date() - timedelta(weeks=8)
    app_rows = (
        db.session.query(func.date(Application.applied_at).label('d'), func.count(Application.id))
        .filter(Application.applied_at >= eight_weeks_ago)
        .group_by(func.date(Application.applied_at))
        .all()
    )
    app_map = {str(r[0]): r[1] for r in app_rows}
    app_labels, app_counts = [], []
    for i in range(7, -1, -1):
        week_start = datetime.utcnow().date() - timedelta(weeks=i, days=datetime.utcnow().weekday())
        count = sum(app_map.get((week_start + timedelta(days=d)).isoformat(), 0) for d in range(7))
        app_labels.append(week_start.strftime('%b %d'))
        app_counts.append(count)

    # Jobs by status (single query)
    job_status_rows = (
        db.session.query(Job.status, func.count(Job.id))
        .group_by(Job.status).all()
    )
    job_status_labels = [r[0] for r in job_status_rows]
    job_status_counts = [r[1] for r in job_status_rows]

    return render_template(
        'admin/dashboard.html',
        page_title='Dashboard',
        total_users=total_users,
        candidates=candidates,
        employers=employers,
        partner_companies=partner_companies,
        active_jobs=active_jobs,
        pending_complaints=pending_complaints,
        in_review_complaints=in_review_complaints,
        resolved_complaints=resolved_complaints,
        rejected_complaints=rejected_complaints,
        pending_employers=pending_employers,
        pending_verifications=pending_verifications,
        verified_employers=verified_employers,
        rejected_employers=rejected_employers,
        pending_jobs=pending_jobs,
        applications_this_week=applications_this_week,
        recent_employer=recent_employer,
        recent_logs=recent_logs,
        signup_labels=signup_labels,
        signup_counts=signup_counts,
        app_labels=app_labels,
        app_counts=app_counts,
        job_status_labels=job_status_labels,
        job_status_counts=job_status_counts,
    )


# ---------------------------------------------------------------------------
# Users (Exclude non-existent users & Eager-load relationships in 1 query)
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
@admin_required
def manage_users():
    page = request.args.get('page', 1, type=int)
    role_filter = request.args.get('role', '')
    search = request.args.get('q', '')

    # Filter out deactivated/ghost accounts
    query = User.query.filter(
        User.role.in_(['candidate', 'employer', 'admin']),
        User.approval_status != 'deactivated'
    ).options(
        joinedload(User.candidate),
        joinedload(User.recruiter).joinedload(Recruiter.company)
    )

    if role_filter:
        query = query.filter(User.role == role_filter)
    if search:
        query = query.filter(or_(
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
        ))

    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False,
    )
    return render_template(
        'admin/users.html',
        page_title='User Management',
        users=users,
        role_filter=role_filter,
        search=search,
    )


@admin_bp.route('/users/<int:user_id>')
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    extra = {}
    if user.candidate:
        extra['profile'] = user.candidate
        extra['applications'] = user.candidate.applications.options(
            joinedload(Application.job).joinedload(Job.company)
        ).all()
    elif user.recruiter:
        extra['profile'] = user.recruiter
        extra['company'] = user.recruiter.company
    return render_template('admin/user_detail.html', page_title='User Details', user=user, **extra)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin():
        active_admins = User.query.filter_by(role='admin', is_active=True).count()
        if user.is_active and active_admins <= 1:
            flash('Cannot deactivate the last active admin account.', 'danger')
        else:
            user.is_active = not user.is_active
            create_audit_log(_get_admin_id(), f'user_{"activated" if user.is_active else "deactivated"}', 'User', user.id)
            db.session.commit()
            flash(f'Admin {"activated" if user.is_active else "deactivated"}.', 'success')
        return redirect(url_for('admin.manage_users'))

    user.is_active = not user.is_active
    create_audit_log(
        _get_admin_id(),
        f'user_{"activated" if user.is_active else "deactivated"}',
        'User', user.id,
    )
    db.session.commit()
    flash(f'User {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.manage_users'))


# ---------------------------------------------------------------------------
# Employer Verification Engine (Only real valid users & Ultra Fast Joined Query)
# ---------------------------------------------------------------------------

@admin_bp.route('/employers')
@admin_required
def manage_employers():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()

    # Fast count aggregations for tabs only considering real employers in database
    base_company_query = (
        Company.query.join(Recruiter, Company.id == Recruiter.company_id)
        .join(User, and_(Recruiter.user_id == User.id, User.approval_status != 'deactivated', User.role == 'employer'))
    )

    pending_count = base_company_query.filter(
        or_(Company.verification_status == 'Pending Verification', Company.verification_status == 'pending', Company.verification_status.is_(None))
    ).count()
    approved_count = base_company_query.filter(
        or_(Company.verification_status == 'Approved', Company.is_verified.is_(True))
    ).count()
    rejected_count = base_company_query.filter(Company.verification_status == 'Rejected').count()
    flagged_count = base_company_query.filter(Company.verification_status == 'Flagged').count()
    all_count = base_company_query.count()

    status_filter = request.args.get('status')
    if status_filter is None:
        status_filter = 'Pending Verification' if pending_count > 0 else ''

    query = base_company_query
    if status_filter == 'Pending Verification':
        query = query.filter(or_(
            Company.verification_status == 'Pending Verification',
            Company.verification_status == 'pending',
            Company.verification_status.is_(None)
        ))
    elif status_filter == 'Approved':
        query = query.filter(or_(Company.verification_status == 'Approved', Company.is_verified.is_(True)))
    elif status_filter:
        query = query.filter(Company.verification_status == status_filter)

    if search:
        query = query.filter(or_(
            Company.name.ilike(f'%{search}%'),
            Company.domain.ilike(f'%{search}%'),
            Company.official_email.ilike(f'%{search}%'),
            Company.ntn_id.ilike(f'%{search}%'),
        ))

    companies = query.order_by(
        desc(User.last_login_at),
        desc(User.created_at),
        desc(Company.id)
    ).paginate(
        page=page, per_page=20, error_out=False
    )

    verified_data = []
    for comp in companies.items:
        email_domain = ''
        if comp.official_email and '@' in comp.official_email:
            email_domain = comp.official_email.split('@')[-1].lower()
        
        web_domain = ''
        if comp.website:
            web_domain = comp.website.lower().replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
        elif comp.domain:
            web_domain = comp.domain.lower().replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]

        domain_matched = bool(email_domain and web_domain and (email_domain in web_domain or web_domain in email_domain))
        verified_data.append({
            'company': comp,
            'email_domain': email_domain,
            'web_domain': web_domain,
            'domain_matched': domain_matched,
        })

    return render_template(
        'admin/employers.html',
        page_title='Employer Verification Engine',
        companies=companies,
        verified_data=verified_data,
        status_filter=status_filter,
        search=search,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        flagged_count=flagged_count,
        all_count=all_count,
    )


@admin_bp.route('/employers/<int:company_id>/<action>', methods=['POST'])
@admin_required
def verify_employer(company_id, action):
    company = Company.query.get_or_404(company_id)
    if action == 'approve':
        company.verification_status = 'Approved'
        company.is_verified = True
        company.rejection_reason = None
        create_audit_log(_get_admin_id(), 'employer_approved', 'Company', company.id)
        db.session.commit()
        flash(f'Employer "{company.name}" has been successfully approved.', 'success')
    elif action == 'reject':
        reason = request.form.get('reason', '').strip()
        company.verification_status = 'Rejected'
        company.is_verified = False
        company.rejection_reason = reason or 'Application rejected by administrator.'
        create_audit_log(_get_admin_id(), 'employer_rejected', 'Company', company.id, details=reason)
        db.session.commit()
        flash(f'Employer "{company.name}" has been rejected.', 'warning')
    elif action == 'flag':
        company.verification_status = 'Flagged'
        company.is_verified = False
        create_audit_log(_get_admin_id(), 'employer_flagged', 'Company', company.id)
        db.session.commit()
        flash(f'Employer "{company.name}" has been flagged for investigation.', 'danger')
    
    return redirect(url_for('admin.manage_employers'))


@admin_bp.route('/candidates/<int:candidate_id>/verify-location', methods=['POST'])
@admin_required
def verify_candidate_location(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    action = request.form.get('action', 'verify')
    
    if action == 'verify':
        candidate.is_location_verified = True
        candidate.location_verified_at = datetime.utcnow()
        candidate.location_verified_by_id = _get_admin_id()
        create_audit_log(_get_admin_id(), 'candidate_location_verified', 'Candidate', candidate.id)
        db.session.commit()
        flash(f'Location for candidate "{candidate.full_name}" is now Verified.', 'success')
    else:
        candidate.is_location_verified = False
        candidate.location_verified_at = None
        candidate.location_verified_by_id = None
        create_audit_log(_get_admin_id(), 'candidate_location_unverified', 'Candidate', candidate.id)
        db.session.commit()
        flash(f'Location verification removed for candidate "{candidate.full_name}".', 'info')

    return redirect(request.referrer or url_for('admin.manage_users'))


# ---------------------------------------------------------------------------
# Jobs (Admin Management & Moderation — View, Unpublish with Reason, Re-Publish)
# ---------------------------------------------------------------------------

@admin_bp.route('/jobs')
@admin_required
def manage_jobs():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('q', '').strip()

    # Base query joined with valid active companies & recruiters
    base_query = (
        Job.query.join(Company, Job.company_id == Company.id)
        .join(Recruiter, Company.id == Recruiter.company_id)
        .join(User, and_(Recruiter.user_id == User.id, User.approval_status != 'deactivated'))
    )

    # Status counts aggregation for filter tabs
    status_counts = {
        'all': base_query.count(),
        'active': base_query.filter(Job.status == 'active').count(),
        'unpublished': base_query.filter(or_(Job.status == 'unpublished', Job.approval_status == 'unpublished', Job.unpublish_reason.isnot(None))).count(),
        'paused': base_query.filter(Job.status == 'paused').count(),
        'closed': base_query.filter(Job.status == 'closed').count(),
    }

    query = base_query.options(joinedload(Job.company), joinedload(Job.category), joinedload(Job.posted_by_recruiter))
    
    if status_filter == 'unpublished':
        query = query.filter(or_(Job.status == 'unpublished', Job.approval_status == 'unpublished', Job.unpublish_reason.isnot(None)))
    elif status_filter:
        query = query.filter(Job.status == status_filter)

    if search:
        query = query.filter(or_(
            Job.title.ilike(f'%{search}%'),
            Company.name.ilike(f'%{search}%'),
            Job.location.ilike(f'%{search}%'),
        ))

    jobs = query.order_by(Job.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False,
    )
    return render_template(
        'admin/jobs.html',
        page_title='Job Moderation & Directory',
        jobs=jobs,
        status_filter=status_filter,
        status_counts=status_counts,
        search=search,
    )


@admin_bp.route('/jobs/<int:job_id>')
@admin_bp.route('/jobs/<int:job_id>/preview')
@admin_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    return render_template('admin/job_preview.html', job=job)


@admin_bp.route('/jobs/<int:job_id>/unpublish', methods=['POST'])
@admin_required
def unpublish_job(job_id):
    """
    Admin unpublishes a job listing with a mandatory reason.
    Removes job from public views and alerts the employer on their dashboard.
    """
    job = Job.query.get_or_404(job_id)
    reason = (request.form.get('reason') or '').strip()
    custom_reason = (request.form.get('custom_reason') or '').strip()
    final_reason = custom_reason if reason == 'Other' and custom_reason else (reason or 'Non-compliant listing details')

    job.status = 'unpublished'
    job.approval_status = 'unpublished'
    job.unpublish_reason = final_reason

    # Notify employer on dashboard
    if job.posted_by_recruiter and job.posted_by_recruiter.user_id:
        db.session.add(Notification(
            user_id=job.posted_by_recruiter.user_id,
            message=f"⚠️ Your job listing '{job.title}' was unpublished by platform administration because: {final_reason}. Please edit your job to resolve this issue.",
            type='job_unpublished',
        ))

    create_audit_log(_get_admin_id(), 'job_unpublished', 'Job', job.id, details=f"Reason: {final_reason}")
    db.session.commit()
    flash(f'Job "{job.title}" has been unpublished. Employer has been notified with the reason.', 'warning')
    return redirect(request.referrer or url_for('admin.manage_jobs'))


@admin_bp.route('/jobs/<int:job_id>/publish', methods=['POST'])
@admin_required
def publish_job(job_id):
    """
    Admin re-publishes a corrected or approved job listing.
    Restores job to active status and notifies the employer.
    """
    job = Job.query.get_or_404(job_id)
    job.status = 'active'
    job.approval_status = 'approved'
    job.unpublish_reason = None

    # Notify employer
    if job.posted_by_recruiter and job.posted_by_recruiter.user_id:
        db.session.add(Notification(
            user_id=job.posted_by_recruiter.user_id,
            message=f"✓ Great news! Your job listing '{job.title}' has been reviewed and re-published live on CareerPearls.",
            type='job_published',
        ))

    create_audit_log(_get_admin_id(), 'job_published', 'Job', job.id)
    db.session.commit()
    flash(f'Job "{job.title}" has been re-published live on the platform.', 'success')
    return redirect(request.referrer or url_for('admin.manage_jobs'))


@admin_bp.route('/jobs/<int:job_id>/<action>', methods=['POST'])
@admin_required
def moderate_job(job_id, action):
    job = Job.query.get_or_404(job_id)
    if action in ('approve', 'publish'):
        return redirect(url_for('admin.publish_job', job_id=job.id), code=307)
    elif action in ('reject', 'unpublish'):
        return redirect(url_for('admin.unpublish_job', job_id=job.id), code=307)
    elif action == 'close':
        job.status = 'closed'
        create_audit_log(_get_admin_id(), 'job_closed', 'Job', job.id)
        db.session.commit()
        flash(f'Job "{job.title}" closed.', 'info')
    return redirect(url_for('admin.manage_jobs'))


# ---------------------------------------------------------------------------
# Complaints (Fast Status Aggregation & Relationship Eager Loading)
# ---------------------------------------------------------------------------

@admin_bp.route('/complaints')
@admin_required
def manage_complaints():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('q', '').strip()

    # Fast single aggregation query for counts (Case-Insensitive & robust)
    status_counts_raw = dict(
        db.session.query(func.lower(Complaint.status), func.count(Complaint.id))
        .group_by(func.lower(Complaint.status))
        .all()
    )
    pending_count = status_counts_raw.get('pending', 0) + status_counts_raw.get('open', 0) + status_counts_raw.get(None, 0)
    in_review_count = status_counts_raw.get('in review', 0) + status_counts_raw.get('under review', 0) + status_counts_raw.get('in progress', 0)
    resolved_count = status_counts_raw.get('resolved', 0) + status_counts_raw.get('closed', 0)
    rejected_count = status_counts_raw.get('rejected', 0) + status_counts_raw.get('dismissed', 0)
    total_count = sum(status_counts_raw.values())

    query = Complaint.query.options(
        joinedload(Complaint.complainant),
        joinedload(Complaint.raised_by_user)
    )
    if status_filter == 'Pending':
        query = query.filter(or_(func.lower(Complaint.status).in_(['pending', 'open']), Complaint.status.is_(None)))
    elif status_filter == 'In Review':
        query = query.filter(func.lower(Complaint.status).in_(['in review', 'under review', 'in progress']))
    elif status_filter == 'Resolved':
        query = query.filter(func.lower(Complaint.status).in_(['resolved', 'closed']))
    elif status_filter in ('Rejected', 'Dismissed'):
        query = query.filter(func.lower(Complaint.status).in_(['rejected', 'dismissed']))
    elif status_filter:
        query = query.filter(func.lower(Complaint.status) == status_filter.lower())

    if search:
        query = query.filter(or_(
            Complaint.ticket_id.ilike(f'%{search}%'),
            Complaint.subject.ilike(f'%{search}%'),
            Complaint.category.ilike(f'%{search}%'),
            Complaint.description.ilike(f'%{search}%'),
            Complaint.reported_entity_type.ilike(f'%{search}%'),
            Complaint.complainant_name.ilike(f'%{search}%'),
            Complaint.complainant_email.ilike(f'%{search}%'),
        ))

    complaints_list = query.order_by(Complaint.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False,
    )
    return render_template(
        'admin/complaints.html',
        page_title='Complaints Management',
        complaints=complaints_list,
        status_filter=status_filter,
        search=search,
        pending_count=pending_count,
        in_review_count=in_review_count,
        resolved_count=resolved_count,
        rejected_count=rejected_count,
        total_count=total_count,
    )


@admin_bp.route('/complaints/<int:complaint_id>/update', methods=['POST'])
@admin_required
def update_complaint(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    raw_status = request.form.get('status', 'Pending').strip()
    admin_note = request.form.get('admin_note', '').strip()
    send_email = bool(request.form.get('send_email'))

    status_map = {
        'pending': 'Pending',
        'open': 'Pending',
        'in review': 'In Review',
        'in_review': 'In Review',
        'under review': 'In Review',
        'in progress': 'In Review',
        'resolved': 'Resolved',
        'closed': 'Resolved',
        'rejected': 'Rejected',
        'dismissed': 'Rejected',
    }
    new_status = status_map.get(raw_status.lower(), raw_status or 'Pending')

    old = complaint.status
    complaint.status = new_status
    if admin_note:
        complaint.admin_note = admin_note
    complaint.updated_at = datetime.utcnow()

    # In-app notification for complainant if registered user
    if complaint.user_id:
        try:
            db.session.add(Notification(
                user_id=complaint.user_id,
                message=f"Your complaint ticket {complaint.ticket_id or f'#CMP-{complaint.id}'} status is now {new_status}." + (f" Note: {admin_note}" if admin_note else ""),
                type='system'
            ))
        except Exception as e:
            pass

    # CRITICAL: Commit status and notes to database
    db.session.commit()

    # Send email notification to complainant if requested
    if send_email:
        to_email = complaint.sender_email
        to_name = complaint.sender_name
        ticket_id = complaint.ticket_id or f'#CMP-{complaint.id}'
        try:
            if to_email and '@' in to_email:
                send_complaint_status_update_email(
                    to_email, to_name, ticket_id, new_status, 
                    admin_note=admin_note,
                    category=complaint.category or '',
                    subject_text=complaint.subject or '',
                    description=complaint.description or ''
                )
        except Exception as e:
            pass

    create_audit_log(
        _get_admin_id(),
        f'complaint_{new_status.lower().replace(" ", "_")}',
        'Complaint', complaint.id,
        details=f"Status changed from {old} to {new_status}. Note: {admin_note}"
    )
    ticket_label = complaint.ticket_id or f'#CMP-{complaint.id}'
    flash(f'Complaint ticket {ticket_label} successfully updated to {new_status}.', 'success')
    return redirect(url_for('admin.manage_complaints'))


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@admin_bp.route('/audit-logs')
@admin_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    user_filter = request.args.get('user_id', type=int)
    action_filter = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = AuditLog.query.options(joinedload(AuditLog.user))
    if user_filter:
        query = query.filter(AuditLog.user_id == user_filter)
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(AuditLog.created_at <= datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59))

    logs = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False,
    )
    all_users = User.query.filter(User.role == 'admin').all()

    return render_template(
        'admin/audit_logs.html',
        page_title='Audit Logs',
        logs=logs,
        user_filter=user_filter,
        action_filter=action_filter,
        date_from=date_from,
        date_to=date_to,
        admin_users=all_users,
    )


@admin_bp.route('/audit-logs/export')
@admin_required
def export_audit_logs():
    user_filter = request.args.get('user_id', type=int)
    action_filter = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = AuditLog.query.options(joinedload(AuditLog.user))
    if user_filter:
        query = query.filter(AuditLog.user_id == user_filter)
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(AuditLog.created_at <= datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59))

    rows = query.order_by(AuditLog.created_at.desc()).limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Timestamp (UTC)', 'Admin / User ID', 'User Name', 'Action', 'Target Type', 'Target ID', 'Details'])
    for log in rows:
        user_name = log.user.name if log.user else 'System / Unknown'
        writer.writerow([
            log.id,
            log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            log.user_id or '',
            user_name,
            log.action,
            log.target_type or '',
            log.target_id or '',
            getattr(log, 'details', '') or '',
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=audit_logs_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return response


# ---------------------------------------------------------------------------
# Categories (Optimized single-query job counts)
# ---------------------------------------------------------------------------

@admin_bp.route('/categories')
@admin_required
def manage_categories():
    categories = JobCategory.query.order_by(JobCategory.name).all()
    # Fast batch counts
    job_counts = dict(
        db.session.query(Job.category_id, func.count(Job.id))
        .group_by(Job.category_id)
        .all()
    )
    cat_data = [
        {'category': cat, 'job_count': job_counts.get(cat.id, 0)}
        for cat in categories
    ]
    return render_template(
        'admin/categories.html',
        page_title='Job Categories',
        categories=cat_data,
    )


@admin_bp.route('/categories/add', methods=['POST'])
@admin_required
def add_category():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Category name is required.', 'danger')
        return redirect(url_for('admin.manage_categories'))
    if JobCategory.query.filter_by(name=name).first():
        flash('Category already exists.', 'danger')
        return redirect(url_for('admin.manage_categories'))
    cat = JobCategory(name=name)
    db.session.add(cat)
    db.session.flush()
    create_audit_log(_get_admin_id(), 'category_created', 'JobCategory', cat.id)
    db.session.commit()
    flash(f'Category "{name}" created.', 'success')
    return redirect(url_for('admin.manage_categories'))


@admin_bp.route('/categories/<int:cat_id>/edit', methods=['POST'])
@admin_required
def edit_category(cat_id):
    cat = JobCategory.query.get_or_404(cat_id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Category name is required.', 'danger')
        return redirect(url_for('admin.manage_categories'))
    cat.name = name
    create_audit_log(_get_admin_id(), 'category_updated', 'JobCategory', cat.id)
    db.session.commit()
    flash('Category updated.', 'success')
    return redirect(url_for('admin.manage_categories'))


@admin_bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@admin_required
def delete_category(cat_id):
    cat = JobCategory.query.get_or_404(cat_id)
    job_count = Job.query.filter_by(category_id=cat.id).count()
    if job_count > 0:
        flash(f'Cannot delete: {job_count} jobs use this category.', 'danger')
        return redirect(url_for('admin.manage_categories'))
    create_audit_log(_get_admin_id(), 'category_deleted', 'JobCategory', cat.id)
    db.session.delete(cat)
    db.session.commit()
    flash('Category deleted.', 'success')
    return redirect(url_for('admin.manage_categories'))


# ---------------------------------------------------------------------------
# Settings & Context
# ---------------------------------------------------------------------------

@admin_bp.route('/settings')
@admin_required
def settings():
    return render_template('admin/settings.html', page_title='Settings')


@admin_bp.route('/moderation')
@admin_required
def moderation_redirect():
    return redirect(url_for('admin.manage_jobs'))


@admin_bp.context_processor
def inject_admin_context():
    admin = get_current_admin()
    return {'admin_user': admin, 'current_user': admin if admin else current_user}
