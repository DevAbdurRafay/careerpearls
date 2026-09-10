from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, session, current_app, jsonify
from flask_login import login_required, current_user, logout_user
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Job, JobCategory, JobSkill, Application, Interview, Offer,
    CompanyHiringField, Candidate, Resume, Recruiter, Message, Notification,
    log_status_change, create_audit_log, can_post_job,
    FIELD_OPTIONS, ORGANIZATION_TYPE_OPTIONS, COMPANY_SIZE_OPTIONS,
    EMPLOYMENT_TYPE_OPTIONS, WORK_MODE_OPTIONS,
)
from app.employer.forms import (
    CompanyProfileForm, JobPostForm, ApplicationStatusForm, InterviewScheduleForm
)
from app.utils import role_required, get_recruiter_or_403, job_belongs_to_recruiter, save_upload, save_base64_image
from app.email_utils import (
    send_interview_call_email, send_interview_modified_email,
    send_application_rejection_email, send_direct_employer_email,
    send_shortlisted_email, send_candidate_hired_email,
    send_interview_failed_email, send_interview_rescheduled_email
)
from app.safe import gattr
from app.button_utils import (
    safe_button_handler, safe_get_recruiter, safe_get_company, 
    safe_flash_success, safe_flash_error, safe_redirect, safe_execute_db_operation
)

employer_bp = Blueprint('employer', __name__, template_folder='templates')


@employer_bp.before_request
def employer_guards():
    if not current_user.is_authenticated:
        return None
    if current_user.needs_oauth_onboarding():
        return redirect(url_for('auth.oauth_onboarding'))
    if current_user.is_employer():
        recruiter = current_user.recruiter
        if recruiter and recruiter.company and not recruiter.company.onboarding_complete:
            # Only force onboarding when trying to access employer-specific dashboard pages
            # Allow access to onboarding page, logout, and other public pages
            allowed = {'employer.onboarding', 'auth.logout', 'auth.oauth_onboarding', 'static'}
            if request.endpoint not in allowed:
                return redirect(url_for('employer.onboarding'))


@employer_bp.route('/onboarding', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def onboarding():
    recruiter = get_recruiter_or_403()
    company = recruiter.company

    if request.method == 'POST':
        org_name = (request.form.get('organization_name') or '').strip()
        domain = (request.form.get('domain') or '').strip()
        official_email = (request.form.get('official_email') or '').strip()
        ntn_id = (request.form.get('ntn_id') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        industry = (request.form.get('industry') or '').strip()
        org_type = request.form.get('organization_type')
        company_size = request.form.get('company_size')
        hiring_fields = request.form.getlist('hiring_fields')
        employment_types = request.form.getlist('employment_types')

        if not org_name:
            flash('Please enter your organization name.', 'warning')
            return redirect(url_for('employer.onboarding'))
        if not industry:
            flash('Please enter your industry.', 'warning')
            return redirect(url_for('employer.onboarding'))

        founded_date_str = request.form.get('founded_date')
        if not founded_date_str:
            flash('Please enter the date your organization was founded.', 'warning')
            return redirect(url_for('employer.onboarding'))
        try:
            founded_date = datetime.strptime(founded_date_str, '%Y-%m-%d').date()
            if founded_date > datetime.utcnow().date():
                flash('Founded date cannot be in the future.', 'warning')
                return redirect(url_for('employer.onboarding'))
            company.founded_date = founded_date
        except ValueError:
            flash('Invalid founded date format.', 'warning')
            return redirect(url_for('employer.onboarding'))

        company.name = org_name
        company.domain = domain or None
        company.official_email = official_email or None
        company.ntn_id = ntn_id or None
        company.phone = phone or None
        company.industry = industry
        company.organization_type = org_type
        company.company_size = company_size
        company.employment_types = ', '.join(employment_types) if employment_types else None
        company.verification_status = 'Pending Verification'
        company.is_verified = False

        company.hiring_fields.delete()
        for field in hiring_fields:
            db.session.add(CompanyHiringField(company_id=company.id, field_name=field))
        company.onboarding_complete = True
        db.session.commit()
        flash('Your organization profile is registered! Your account status is Pending Verification by Super Admin.', 'success')
        return redirect(url_for('employer.dashboard'))

    selected_fields = [f.field_name for f in company.hiring_fields.all()]
    selected_employment = (company.employment_types or '').split(', ') if company.employment_types else []
    return render_template(
        'employer/onboarding.html',
        company=company,
        field_options=FIELD_OPTIONS,
        org_type_options=ORGANIZATION_TYPE_OPTIONS,
        size_options=COMPANY_SIZE_OPTIONS,
        employment_options=EMPLOYMENT_TYPE_OPTIONS,
        selected_fields=selected_fields,
        selected_employment=selected_employment,
        now=datetime.utcnow(),
    )


@employer_bp.route('/talent')
@login_required
@role_required('employer')
def find_talent():
    """
    CANDIDATE SOURCING PRIVACY RULE (CRITICAL):
    Employers CANNOT search or browse a raw database of candidates directly on their dashboard.
    """
    flash('Candidate Sourcing Privacy Rule: Raw talent browsing is disabled. Candidate details are accessible ONLY when a candidate actively applies to your job postings.', 'info')
    return redirect(url_for('employer.manage_applications'))


@employer_bp.route('/candidate/<int:candidate_id>')
@login_required
@role_required('employer')
def view_candidate_profile(candidate_id):
    recruiter = get_recruiter_or_403()
    company = recruiter.company
    candidate = Candidate.query.get_or_404(candidate_id)

    # Candidate Privacy Enforcement: check if candidate has applied to employer's jobs
    company_jobs = Job.query.filter_by(company_id=company.id).all()
    company_job_ids = [j.id for j in company_jobs]

    app_id = request.args.get('application_id', type=int)
    has_applied = None
    if app_id and company_job_ids:
        has_applied = Application.query.filter(
            Application.id == app_id,
            Application.candidate_id == candidate.id,
            Application.job_id.in_(company_job_ids)
        ).first()

    if not has_applied and company_job_ids:
        has_applied = Application.query.filter(
            Application.candidate_id == candidate.id,
            Application.job_id.in_(company_job_ids)
        ).order_by(Application.id.desc()).first()

    if not has_applied:
        # Return error HTML for AJAX requests instead of redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return '<div class="p-4 text-center"><i class="bi bi-shield-lock display-4 text-warning d-block mb-3"></i><p class="text-danger fw-bold">Access Restricted</p><p class="text-muted small">You can only view details of candidates who have actively applied to your job postings.</p></div>', 403
        flash('Candidate Sourcing Privacy Rule: You can only view details of candidates who have actively applied to your job postings.', 'danger')
        return redirect(url_for('employer.manage_applications'))

    try:
        work_mode_labels = dict(WORK_MODE_OPTIONS)
        return render_template(
            'employer/_candidate_modal_body.html',
            candidate=candidate,
            work_mode_labels=work_mode_labels,
            Resume=Resume,
            application=has_applied,
        )
    except Exception as e:
        current_app.logger.error(f"Error rendering candidate profile: {e}")
        # Return error HTML for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return '<div class="p-4 text-center"><i class="bi bi-exclamation-triangle display-4 text-danger d-block mb-3"></i><p class="text-danger fw-bold">Error Loading Profile</p><p class="text-muted small">Failed to load candidate profile. Please try again.</p></div>', 500
        flash('Failed to load candidate profile. Please try again.', 'danger')
        return redirect(url_for('employer.manage_applications'))


@employer_bp.route('/dashboard')
@login_required
@role_required('employer')
def dashboard():
    recruiter = get_recruiter_or_403()
    company = recruiter.company
    if company:
        try:
            db.session.refresh(company)
        except Exception:
            pass

    jobs = Job.query.filter_by(company_id=company.id).all()
    job_ids = [j.id for j in jobs]

    recent_applications = (
        Application.query.join(Job)
        .filter(
            Job.company_id == company.id,
            Application.status != 'Withdrawn'
        )
        .order_by(Application.applied_at.desc())
        .options(
            joinedload(Application.job).joinedload(Job.company),
            joinedload(Application.candidate)
        )
        .limit(10)
        .all()
    ) if job_ids else []

    status_counts = {}
    if job_ids:
        rows = (
            db.session.query(Application.status, func.count(Application.id))
            .filter(Application.job_id.in_(job_ids))
            .group_by(Application.status)
            .all()
        )
        status_counts = {s: c for s, c in rows}

        # Ensure all standard funnel stages are present (even if count is 0)
        funnel_stages = ['Applied', 'Screening', 'Under Review', 'Shortlisted', 'Interview Scheduled', 'Selected', 'Rejected']
        for stage in funnel_stages:
            if stage not in status_counts:
                status_counts[stage] = 0

    return render_template(
        'employer/dashboard.html',
        company=company,
        recent_applications=recent_applications,
        status_counts=status_counts,
        active_jobs_count=Job.query.filter(Job.company_id == company.id, Job.status == 'active', or_(Job.is_hired == False, Job.is_hired.is_(None))).count(),
        total_jobs_count=Job.query.filter_by(company_id=company.id).count(),
        now=datetime.utcnow(),
    )


@employer_bp.route('/company', methods=['GET', 'POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.company_profile')
def company_profile():
    try:
        recruiter = get_recruiter_or_403()
        company = recruiter.company
        form = CompanyProfileForm(obj=company)

        # Pre-populate WTForms data on GET request so they don't show "None" string
        if request.method == 'GET':
            form.recruiter_name.data = recruiter.name or ''
            form.title.data = recruiter.title or ''

        # Handle logo upload
        if request.form.get('form_type') == 'logo':
            cropped = request.form.get('cropped_image')
            file = request.files.get('logo')
            if cropped or (file and file.filename):
                try:
                    if cropped:
                        filename = save_base64_image(cropped, current_app.config['UPLOAD_FOLDER'])
                        if not filename:
                            safe_flash_error('Invalid base64 image data. Please try a different image.')
                            return safe_redirect('employer.company_profile')
                    elif file and file.filename:
                        filename = save_upload(file, current_app.config['UPLOAD_FOLDER'], {'png', 'jpg', 'jpeg', 'webp'})
                        if not filename:
                            safe_flash_error('Invalid file format. Please use PNG, JPG, or WEBP.')
                            return safe_redirect('employer.company_profile')
                    else:
                        safe_flash_error('No image data provided.')
                        return safe_redirect('employer.company_profile')
                    
                    if filename:
                        company.logo_path = filename
                        db.session.commit()
                        safe_flash_success('Company logo updated successfully.')
                    else:
                        safe_flash_error('Failed to process image. Please try again.')
                except IOError as e:
                    current_app.logger.error(f"Logo file I/O error: {e}")
                    db.session.rollback()
                    safe_flash_error('File save error. Please check file permissions and try again.')
                except Exception as e:
                    current_app.logger.error(f"Logo upload error: {e}", exc_info=True)
                    db.session.rollback()
                    safe_flash_error(f'Upload failed: {str(e)}')
            else:
                safe_flash_error('Please choose a logo to upload.')
            return safe_redirect('employer.company_profile')

        if request.form.get('action') != 'deactivate' and form.validate_on_submit():
            # Manually copy company form fields to avoid WTForms AttributeError on non-model fields (recruiter_name/title)
            company.name = form.name.data
            company.domain = form.domain.data
            company.official_email = form.official_email.data
            company.ntn_id = form.ntn_id.data
            company.phone = form.phone.data
            company.location = form.location.data
            company.industry = form.industry.data
            company.company_size = form.company_size.data
            company.website = form.website.data
            company.description = form.description.data
            
            # Update recruiter fields
            recruiter.name = form.recruiter_name.data or ''
            recruiter.title = form.title.data or ''
            
            founded_date_str = request.form.get('founded_date')
            if founded_date_str:
                try:
                    founded_date = datetime.strptime(founded_date_str, '%Y-%m-%d').date()
                    if founded_date <= datetime.utcnow().date():
                        company.founded_date = founded_date
                except ValueError:
                    pass
            create_audit_log(current_user.id, 'company_updated', 'Company', company.id)
            db.session.commit()
            safe_flash_success('Company profile updated.')
            return safe_redirect('employer.company_profile')

        return render_template(
            'employer/company_profile.html',
            form=form,
            company=company,
            completion_pct=company.calculate_completion_pct(),
        )
    except Exception as e:
        current_app.logger.error(f"Company profile error: {e}", exc_info=True)
        db.session.rollback()
        safe_flash_error('Failed to update company profile. Please try again.')
        return safe_redirect('employer.company_profile')


@employer_bp.route('/deactivate-account', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.company_profile')
def deactivate_account():
    try:
        from app.utils import permanently_delete_user_account
        reason = request.form.get('reason')
        password = request.form.get('password')
        
        if not reason:
            safe_flash_error('Please select a reason for deactivation.')
            return safe_redirect('employer.company_profile')

        if current_user.password_hash:
            if not password or not current_user.check_password(password):
                safe_flash_error('Incorrect password. Account deactivation cancelled.')
                return safe_redirect('employer.company_profile')
        else:
            # Google OAuth user confirmation check
            if not password or password.strip().lower() != current_user.email.strip().lower():
                safe_flash_error('Since you use Google Auth, please enter your email address to confirm deactivation.')
                return safe_redirect('employer.company_profile')

        user_id = current_user.id
        ok, msg = permanently_delete_user_account(user_id)
        if not ok:
            safe_flash_error('Failed to completely delete account records.')
            return safe_redirect('employer.company_profile')

        logout_user()
        session.clear()
        safe_flash_success('Account deactivated successfully. Your profile and all data have been completely removed from CareerPearls.')
        return safe_redirect('auth.login', role='employer')
    except Exception as e:
        current_app.logger.error(f"Employer deactivate error: {e}", exc_info=True)
        db.session.rollback()
        safe_flash_error('Failed to deactivate account. Please try again.')
        return safe_redirect('employer.company_profile')


@employer_bp.route('/post-job', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def post_job():
    recruiter = get_recruiter_or_403()
    company = recruiter.company

    # ── Admin Approval Guard ─────────────────────────────────────────────
    if not company or not company.is_verified:
        flash(
            '🔒 You need Super Admin approval before posting a job. '
            'Your account is currently in Pending Verification status. '
            'Please contact the admin or wait.',
            'danger'
        )
        return redirect(url_for('employer.dashboard'))
    # ────────────────────────────────────────────────────────────────────

    # ── Job Limit Guard (Max 20 Jobs per Employer) ──────────────────────
    allowed, limit_msg = can_post_job(company.id if company else None)
    if not allowed:
        flash(f'⚠️ {limit_msg}', 'warning')
        return redirect(url_for('employer.dashboard'))
    # ────────────────────────────────────────────────────────────────────

    form = JobPostForm()
    form.category_id.choices = [(c.id, c.name) for c in JobCategory.query.order_by(JobCategory.name).all()]

    if form.validate_on_submit():
        if form.closes_at.data and form.closes_at.data < datetime.utcnow():
            flash('Application deadline date cannot be in the past. Please select a future date & time.', 'danger')
            return render_template('employer/post_job.html', form=form)

        job = Job(
            company_id=company.id,
            title=form.title.data.strip(),
            category_id=form.category_id.data,
            description=form.description.data.strip(),
            location=form.location.data.strip(),
            salary_range=form.salary_range.data.strip() if form.salary_range.data else None,
            employment_type=form.employment_type.data,
            experience_required=(form.experience_required.data or '').strip() or None,
            posted_by=recruiter.id,
            closes_at=form.closes_at.data,
            status='active',
            approval_status='approved',
        )
        db.session.add(job)
        db.session.flush()

        if form.skills.data:
            for skill in [s.strip() for s in form.skills.data.split(',') if s.strip()]:
                db.session.add(JobSkill(job_id=job.id, skill_name=skill, is_required=True))

        create_audit_log(current_user.id, 'job_posted', 'Job', job.id)
        db.session.commit()
        
        # Trigger automated job notifications to candidates
        try:
            from app.models import Candidate
            from app.email_utils import send_job_notifier_email
            subscribed_cands = Candidate.query.filter(
                or_(Candidate.job_notifier_enabled == True, Candidate.job_notifier_enabled.is_(None))
            ).all()
            for cand in subscribed_cands:
                if cand.user and cand.user.email:
                    send_job_notifier_email(cand, job)
        except Exception as mail_err:
            current_app.logger.warning(f"Job notification email error: {mail_err}")

        flash('Job posted successfully and is now visible to candidates!', 'success')
        return redirect(url_for('employer.dashboard'))

    if request.method == 'GET' and not form.closes_at.data:
        form.closes_at.data = datetime.utcnow() + timedelta(days=30)

    return render_template('employer/post_job.html', form=form)



@employer_bp.route('/applications')
@login_required
@role_required('employer')
def manage_applications():
    recruiter = get_recruiter_or_403()
    company = recruiter.company
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    job_filter = request.args.get('job_id', type=int)

    # Calculate comprehensive metrics
    jobs = Job.query.filter_by(company_id=company.id).all()
    job_ids = [j.id for j in jobs]
    active_jobs = Job.query.filter(
        Job.company_id == company.id,
        Job.status == 'active',
        or_(Job.is_hired == False, Job.is_hired.is_(None))
    ).count()

    # Mark all unread applications for this employer as read when visiting applications page
    if job_ids:
        Application.query.filter(
            Application.job_id.in_(job_ids),
            Application.is_read_by_employer == False
        ).update({'is_read_by_employer': True}, synchronize_session=False)
        db.session.commit()

    total_applications = Application.query.filter(
        Application.job_id.in_(job_ids),
        Application.status != 'Withdrawn'
    ).count() if job_ids else 0
    contacted_count = Application.query.filter(Application.job_id.in_(job_ids), Application.status.in_(['Contacted', 'Interview Scheduled'])).count() if job_ids else 0
    rejected_count = Application.query.filter(Application.job_id.in_(job_ids), Application.status == 'Rejected').count() if job_ids else 0
    under_review_count = Application.query.filter(Application.job_id.in_(job_ids), Application.status == 'Under Review').count() if job_ids else 0
    selected = Application.query.filter(Application.job_id.in_(job_ids), Application.status == 'Selected').count() if job_ids else 0

    # Calculate interviews for this week & upcoming days (strictly count distinct active applications)
    now = datetime.utcnow()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=14)

    interviews_this_week = (
        db.session.query(func.count(func.distinct(Interview.application_id)))
        .join(Application, Application.id == Interview.application_id)
        .join(Job, Job.id == Application.job_id)
        .filter(
            Job.company_id == company.id,
            Interview.scheduled_at >= week_start,
            Interview.scheduled_at <= week_end,
            Interview.status.in_(['Scheduled', 'Rescheduled']),
            Application.status.in_(['Interview Scheduled', 'Shortlisted', 'Contacted'])
        )
        .scalar()
    ) or 0

    interviews = Interview.query.join(Application).join(Job).filter(Job.company_id == company.id).count() if job_ids else 0
    shortlisted = Application.query.filter(Application.job_id.in_(job_ids), Application.status == 'Shortlisted').count() if job_ids else 0
    offer_acceptance = round((selected / total_applications * 100), 1) if total_applications else 0

    query = (
        Application.query.join(Job)
        .filter(
            Job.company_id == recruiter.company_id,
            Application.status != 'Withdrawn'
        )
    )
    if status_filter:
        query = query.filter(Application.status == status_filter)
    if job_filter:
        query = query.filter(Application.job_id == job_filter)

    applications = query.order_by(Application.applied_at.desc()).options(
        joinedload(Application.job).joinedload(Job.company),
        joinedload(Application.candidate)
    ).paginate(
        page=page, per_page=15, error_out=False
    )

    company_jobs = Job.query.filter_by(company_id=recruiter.company_id).all()
    status_form = ApplicationStatusForm()
    interview_form = InterviewScheduleForm()

    return render_template(
        'employer/manage_applications.html',
        applications=applications,
        company_jobs=company_jobs,
        company=recruiter.company,
        status_filter=status_filter,
        job_filter=job_filter,
        status_form=status_form,
        interview_form=interview_form,
        Interview=Interview,
        # Dashboard metrics
        active_jobs=active_jobs,
        total_applications=total_applications,
        shortlisted=shortlisted,
        interviews_this_week=interviews_this_week,
        selected=selected,
        offer_acceptance=offer_acceptance,
    )


def get_company_karachi_location(company_name, company_id=None):
    locations = [
        "Suite #504, 5th Floor, Executive Tower, Dolmen Mall Clifton, Marine Drive, Karachi, Pakistan",
        "Level 7, Emerald Tower, Near Do Talwar, Block 5, Clifton, Karachi, Pakistan",
        "Plot 18-C, 7th Commercial Lane, Main Zamzama Boulevard, Phase 5 DHA, Karachi, Pakistan",
        "Tower B, 9th Floor, Skyview Corporate Towers, Main Shahrah-e-Faisal, Karachi, Pakistan",
        "Plot 34-A, Business Avenue, PECHS Block 6, Shahrah-e-Faisal, Karachi, Pakistan",
        "Level 4, Ocean Tower, Block 9, Main Clifton Road, Karachi, Pakistan",
    ]
    if not company_name:
        return locations[0]
    idx = (sum(ord(c) for c in str(company_name)) + (company_id or 0)) % len(locations)
    return locations[idx]


def format_interview_time_ampm(time_str):
    if not time_str:
        return "11:30 AM PKT"
    time_str = str(time_str).strip()
    try:
        dt = datetime.strptime(time_str, '%H:%M')
        return dt.strftime('%I:%M %p') + " PKT"
    except Exception:
        pass
    try:
        dt = datetime.strptime(time_str, '%I:%M %p')
        return dt.strftime('%I:%M %p') + " PKT"
    except Exception:
        pass
    if 'AM' not in time_str.upper() and 'PM' not in time_str.upper():
        return f"{time_str} PKT"
    return time_str


# ---------------------------------------------------------------------------
# Employer Applicant Review Pipeline — 3 STRICT ACTIONS ONLY
# ---------------------------------------------------------------------------

@employer_bp.route('/applications/<int:app_id>/message', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def message_candidate(app_id):
    """
    ACTION 1: Message Directly
    Opens an in-app candidate direct chat under the verified Organization Name
    AND triggers an automated, templated email notification (e.g. Interview Call with Date, Time, Location).
    Updates status to 'Contacted'.
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        body = (request.form.get('message') or '').strip()
        interview_date = request.form.get('interview_date', '').strip()
        raw_interview_time = request.form.get('interview_time', '').strip()
        interview_location = request.form.get('interview_location', '').strip()

        interview_mode = (request.form.get('interview_mode') or 'On-Site').strip()

        if not body:
            safe_flash_error('Please enter a message to send to the candidate.')
            return safe_redirect('employer.manage_applications')

        org_name = gattr(recruiter.company, 'name') or 'Organization'
        org_email = current_user.email or (recruiter.company.email if recruiter.company else 'analysis.workforce@gmail.com')
        karachi_address = get_company_karachi_location(org_name, recruiter.company_id if recruiter else None)

        if not interview_location:
            interview_location = karachi_address

        formatted_time = format_interview_time_ampm(raw_interview_time) if raw_interview_time else "11:30 AM PKT"

        msg_content = f'[{org_name}]\n{body}'
        if interview_date or raw_interview_time or interview_location:
            msg_content += (
                f"\n\n[Official On-Site Interview Details]\n"
                f"• Position: {application.job.title}\n"
                f"• Date: {interview_date or 'Monday'}\n"
                f"• Time: {formatted_time}\n"
                f"• Mode: {interview_mode}\n"
                f"• Venue / Address: {interview_location}\n"
                f"• For Queries Contact: {org_email}"
            )

        cand_user_id = gattr(gattr(application, 'candidate'), 'user_id')
        if not cand_user_id:
            safe_flash_error('Candidate account is unavailable.')
            return safe_redirect('employer.manage_applications')

        db.session.add(Message(
            sender_id=current_user.id,
            receiver_id=cand_user_id,
            application_id=application.id,
            body=msg_content,
        ))
        db.session.add(Notification(
            user_id=cand_user_id,
            message=f"🎉 New message from {org_name} regarding your application for {application.job.title}.",
            type='message',
        ))

        if interview_date:
            try:
                when = datetime.strptime(f'{interview_date} {raw_interview_time or "09:00"}', '%Y-%m-%d %H:%M')
            except ValueError:
                when = datetime.utcnow() + timedelta(days=3)
            db.session.add(Interview(
                application_id=application.id,
                scheduled_at=when,
                mode=interview_mode,
                location_or_link=interview_location or None,
                status='Scheduled',
            ))
        log_status_change(application, 'Contacted', current_user.id)
        create_audit_log(current_user.id, 'candidate_messaged', 'Application', application.id)
        db.session.commit()

        safe_flash_success(f'Message sent directly to {application.candidate.full_name}. Status: Contacted.')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Message candidate error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to send message. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/schedule-interview', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def schedule_interview(app_id):
    """
    Dedicated Official Interview Scheduling Engine:
    - Creates or updates Interview record
    - Sets application.status = 'Interview Scheduled'
    - Logs status change and audit log
    - Dispatches in-app Message with formatted interview details
    - Dispatches high-priority in-app Notification to candidate
    - Dispatches official authenticated email with complete interview details
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        interview_date_str = (request.form.get('interview_date') or '').strip()
        raw_interview_time = (request.form.get('interview_time') or '').strip()
        interview_mode = (request.form.get('interview_mode') or 'On-Site').strip()
        interview_location = (request.form.get('interview_location') or '').strip()
        round_name = (request.form.get('round_name') or 'Official Interview').strip()
        custom_message = (request.form.get('message') or '').strip()

        if not interview_date_str:
            safe_flash_error('Please select a valid date for the interview.')
            return safe_redirect('employer.manage_applications')

        org_name = gattr(recruiter.company, 'name') or 'Organization'
        org_email = current_user.email or (recruiter.company.email if recruiter.company else 'support@careerpearls.com')
        karachi_address = get_company_karachi_location(org_name, recruiter.company_id if recruiter else None)

        if not interview_location:
            interview_location = karachi_address if interview_mode == 'On-Site' else 'Google Meet Video Call'

        formatted_time = format_interview_time_ampm(raw_interview_time) if raw_interview_time else "11:30 AM PKT"

        # Parse datetime
        time_part = "09:00"
        if raw_interview_time:
            # Try to extract 24hr or 12hr time
            try:
                dt_tmp = datetime.strptime(raw_interview_time.replace(' PKT', '').replace(' pkt', '').strip(), '%I:%M %p')
                time_part = dt_tmp.strftime('%H:%M')
            except Exception:
                try:
                    dt_tmp = datetime.strptime(raw_interview_time.strip(), '%H:%M')
                    time_part = dt_tmp.strftime('%H:%M')
                except Exception:
                    time_part = "11:30"

        try:
            scheduled_dt = datetime.strptime(f'{interview_date_str} {time_part}', '%Y-%m-%d %H:%M')
        except ValueError:
            scheduled_dt = datetime.utcnow() + timedelta(days=3)

        # Create or update existing interview (strictly 1 interview record per application)
        all_ivs = Interview.query.filter_by(application_id=application.id).order_by(Interview.id.desc()).all()
        is_update = bool(all_ivs)
        if not all_ivs:
            interview = Interview(
                application_id=application.id,
                scheduled_at=scheduled_dt,
                mode=interview_mode,
                location_or_link=interview_location,
                status='Scheduled',
            )
            db.session.add(interview)
        else:
            interview = all_ivs[0]
            interview.scheduled_at = scheduled_dt
            interview.mode = interview_mode
            interview.location_or_link = interview_location
            interview.status = 'Scheduled'
            # Delete any duplicate older interview rows
            for dup in all_ivs[1:]:
                db.session.delete(dup)

        # Update application status to 'Interview Scheduled'
        log_status_change(application, 'Interview Scheduled', current_user.id)
        create_audit_log(current_user.id, 'interview_schedule_updated' if is_update else 'interview_scheduled', 'Interview', interview.id if interview.id else application.id)

        cand_user_id = gattr(gattr(application, 'candidate'), 'user_id')
        cand_email = gattr(gattr(application.candidate, 'user'), 'email') if application.candidate and application.candidate.user else ''
        cand_name = gattr(application.candidate, 'full_name') or 'Candidate'

        # 1. In-App Message
        if is_update:
            msg_content = (
                f"[{org_name}]\n"
                f"🔄 Interview Schedule Updated: {round_name}\n\n"
                f"• Position: {application.job.title}\n"
                f"• New Date: {interview_date_str}\n"
                f"• New Time: {formatted_time}\n"
                f"• Mode: {interview_mode}\n"
                f"• Venue / Link: {interview_location}\n"
                f"• Queries Contact: {org_email}\n\n"
                f"{custom_message or 'Please note your revised interview schedule.'}"
            )
            notif_msg = f"🔄 Interview Schedule Updated: {org_name} revised your interview for {application.job.title} to {interview_date_str} at {formatted_time}."
            flash_msg = f'🔄 Interview schedule updated for {cand_name}! Revised details sent via email.'
        else:
            msg_content = (
                f"[{org_name}]\n"
                f"📅 Official Interview Call: {round_name}\n\n"
                f"• Position: {application.job.title}\n"
                f"• Date: {interview_date_str}\n"
                f"• Time: {formatted_time}\n"
                f"• Mode: {interview_mode}\n"
                f"• Venue / Address: {interview_location}\n"
                f"• Queries Contact: {org_email}\n\n"
                f"{custom_message or 'We look forward to meeting you for your interview. Please confirm your attendance.'}"
            )
            notif_msg = f"📅 Interview Scheduled: {org_name} has scheduled an interview for {application.job.title} on {interview_date_str} at {formatted_time}."
            flash_msg = f'📅 Interview scheduled successfully for {cand_name}! Official invitation dispatched via email.'

        if cand_user_id:
            db.session.add(Message(
                sender_id=current_user.id,
                receiver_id=cand_user_id,
                application_id=application.id,
                body=msg_content,
            ))
            # 2. In-App Notification
            db.session.add(Notification(
                user_id=cand_user_id,
                message=notif_msg,
                type='interview',
            ))

        db.session.commit()

        # 3. Dispatched Official Email
        if cand_email:
            try:
                # Format accurate Date and Day: e.g. "Monday, Sep 08, 2026"
                try:
                    formatted_date_with_day = scheduled_dt.strftime('%A, %b %d, %Y')
                except Exception:
                    formatted_date_with_day = interview_date_str

                if is_update:
                    send_interview_modified_email(
                        candidate_email=cand_email,
                        candidate_name=cand_name,
                        company_name=org_name,
                        job_title=application.job.title,
                        interview_date=formatted_date_with_day,
                        interview_time=formatted_time,
                        interview_location=interview_location,
                        message_text=custom_message or f"Your interview schedule has been updated for {application.job.title}.",
                        company_email=org_email,
                    )
                else:
                    send_interview_call_email(
                        candidate_email=cand_email,
                        candidate_name=cand_name,
                        company_name=org_name,
                        job_title=application.job.title,
                        interview_date=formatted_date_with_day,
                        interview_time=formatted_time,
                        interview_location=interview_location,
                        message_text=custom_message or f"We are pleased to invite you for an interview for the {application.job.title} position.",
                        company_email=org_email,
                    )
            except Exception as e:
                current_app.logger.error(f"Failed to dispatch interview email: {e}")

        safe_flash_success(flash_msg)
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Schedule interview error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to schedule interview. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/shortlist', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def shortlist_candidate(app_id):
    """
    ACTION: Shortlist Candidate
    Updates application status to 'Shortlisted'.
    Sends congratulatory dashboard notification to candidate.
    Dispatches official Shortlisted email with company query contact.
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        org_name = gattr(recruiter.company, 'name') or 'Organization'
        org_email = current_user.email or (recruiter.company.email if recruiter.company else 'support@careerpearls.com')
        log_status_change(application, 'Shortlisted', current_user.id)

        # Send congratulatory notification to candidate
        cand_user_id = gattr(gattr(application, 'candidate'), 'user_id')
        if cand_user_id:
            db.session.add(Notification(
                user_id=cand_user_id,
                message=f"🎉 Congratulations! You have been Shortlisted by {org_name} for the position of {application.job.title}!",
                type='shortlist',
            ))

        create_audit_log(current_user.id, 'candidate_shortlisted', 'Application', application.id)
        db.session.commit()

        # Dispatch official Shortlisted email notification
        try:
            cand_user = application.candidate.user
            send_shortlisted_email(
                candidate_email=gattr(cand_user, 'email') or '',
                candidate_name=gattr(application.candidate, 'full_name') or 'Candidate',
                company_name=org_name,
                job_title=application.job.title,
                company_email=org_email,
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send shortlisted email: {e}")

        safe_flash_success(f'⭐ {application.candidate.full_name} has been Shortlisted for {application.job.title}! Confirmation email sent.')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Shortlist candidate error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to shortlist candidate. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/unshortlist', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def unshortlist_candidate(app_id):
    """
    ACTION: Remove from Shortlist
    Reverts status back to 'Under Review'.
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        log_status_change(application, 'Under Review', current_user.id)
        create_audit_log(current_user.id, 'candidate_unshortlisted', 'Application', application.id)
        db.session.commit()

        safe_flash_success(f'Shortlist removed for {application.candidate.full_name}. Status reverted to Under Review.')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Unshortlist candidate error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to update status. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/unwait', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def unwait_candidate(app_id):
    """
    ACTION: Un-Wait Candidate
    Toggles status from 'Under Review' back to 'Applied'.
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        log_status_change(application, 'Applied', current_user.id)
        create_audit_log(current_user.id, 'candidate_unwait', 'Application', application.id)
        db.session.commit()

        safe_flash_success(f'Application for {application.candidate.full_name} is now moved back to Active Review.')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Unwait candidate error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to update status. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/wait', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def wait_candidate(app_id):
    """
    ACTION 2: Wait
    Leaves application status as 'Under Review' silently. Candidate is not notified.
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        log_status_change(application, 'Under Review', current_user.id)
        create_audit_log(current_user.id, 'candidate_wait_review', 'Application', application.id)
        db.session.commit()

        safe_flash_success(f'Application for {application.candidate.full_name} is kept Under Review silently.')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Wait candidate error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to update application status. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/reject', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def reject_candidate(app_id):
    """
    ACTION 3: Reject
    Opens a rejection dialog requiring a standard or custom rejection reason selection.
    Sends automated email/dashboard notification to candidate:
    "Your application for the [Job Title] position has been rejected because: [Reason]."
    Updates status to 'Rejected'.
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        reason = (request.form.get('reason') or '').strip()
        custom_reason = (request.form.get('custom_reason') or '').strip()
        final_reason = custom_reason if reason == 'Other' and custom_reason else (reason or 'Position requirements mismatch')

        application.rejection_reason = final_reason
        log_status_change(application, 'Rejected', current_user.id)

        # Candidate dashboard notification
        notif = Notification(
            user_id=application.candidate.user_id,
            message=f"Your application for {application.job.title} at {recruiter.company.name} has been rejected because: {final_reason}.",
            type='rejection',
        )
        db.session.add(notif)

        create_audit_log(current_user.id, 'candidate_rejected', 'Application', application.id, details=f"Reason: {final_reason}")
        db.session.commit()

        # Automated email notification
        try:
            cand_user = application.candidate.user
            send_application_rejection_email(
                candidate_email=cand_user.email,
                candidate_name=application.candidate.full_name,
                company_name=recruiter.company.name,
                job_title=application.job.title,
                reason=final_reason,
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send rejection email: {e}")
            # Continue anyway - the dashboard notification was sent successfully

        safe_flash_success(f'Application rejected. Candidate notified with reason: {final_reason}')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Reject candidate error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to reject application. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/jobs/<int:job_id>/pause', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.dashboard')
def pause_job(job_id):
    try:
        recruiter = get_recruiter_or_403()
        job = Job.query.get_or_404(job_id)
        if not job_belongs_to_recruiter(job, recruiter):
            abort(403)
        job.status = 'paused' if job.status == 'active' else 'active'
        db.session.commit()
        safe_flash_success(f'Job {"paused" if job.status == "paused" else "reactivated"}.')
        return safe_redirect('employer.dashboard')
    except Exception as e:
        current_app.logger.error(f"Pause job error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to update job status. Please try again.')
        return safe_redirect('employer.dashboard')


@employer_bp.route('/jobs/<int:job_id>/delete', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.dashboard')
def delete_job(job_id):
    try:
        recruiter = get_recruiter_or_403()
        job = Job.query.get_or_404(job_id)
        if not job_belongs_to_recruiter(job, recruiter):
            abort(403)
        job.status = 'deleted'
        db.session.commit()
        safe_flash_success('Job listing removed from public view.')
        return safe_redirect('employer.dashboard')
    except Exception as e:
        current_app.logger.error(f"Delete job error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to delete job. Please try again.')
        return safe_redirect('employer.dashboard')


@employer_bp.route('/jobs/<int:job_id>/renew', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.my_jobs')
def renew_job(job_id):
    try:
        recruiter = get_recruiter_or_403()
        job = Job.query.get_or_404(job_id)
        if not job_belongs_to_recruiter(job, recruiter):
            abort(403)
        
        # Extend closes_at deadline by 30 days from now and ensure active status
        job.closes_at = datetime.utcnow() + timedelta(days=30)
        job.status = 'active'
        job.is_hired = False
        job.unpublish_reason = None
        db.session.commit()
        safe_flash_success(f'"{job.title}" has been renewed for 30 days and is now active for candidate applications!')
        return safe_redirect('employer.my_jobs')
    except Exception as e:
        current_app.logger.error(f"Renew job error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to renew job listing. Please try again.')
        return safe_redirect('employer.my_jobs')


@employer_bp.route('/messages')
@login_required
@role_required('employer')
def messages():
    recruiter = get_recruiter_or_403()
    inbox = (
        Message.query.filter(
            or_(Message.sender_id == current_user.id, Message.receiver_id == current_user.id)
        )
        .order_by(Message.sent_at.desc())
        .limit(80)
        .all()
    )
    return render_template('employer/messages.html', messages=inbox, company=recruiter.company)


@employer_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def settings():
    return redirect(url_for('employer.company_profile'))


@employer_bp.route('/interviews/<int:interview_id>/outcome', methods=['POST'])
@employer_bp.route('/applications/<int:interview_id>/interview-outcome', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def record_interview_outcome(interview_id):
    """
    Record interview outcome and update application status accordingly.
    Supports both interview_id and application_id endpoints for maximum reliability.
    """
    try:
        recruiter = get_recruiter_or_403()
        
        # Check if interview_id is an Interview or an Application
        interview = Interview.query.get(interview_id)
        if not interview:
            application = Application.query.get_or_404(interview_id)
            interview = application.interviews.order_by(Interview.id.desc()).first()
            if not interview:
                interview = Interview(
                    application_id=application.id,
                    scheduled_at=datetime.utcnow(),
                    mode='On-Site',
                    status='Completed'
                )
                db.session.add(interview)
                db.session.flush()
        else:
            application = interview.application
        
        # Verify interview belongs to employer's company
        if not application or not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)
        
        outcome = (request.form.get('outcome') or '').strip()
        notes = (request.form.get('notes') or '').strip()
        
        if not outcome:
            safe_flash_error('Please select an interview outcome.')
            return safe_redirect('employer.manage_applications')
        
        org_name = gattr(recruiter.company, 'name') or 'Organization'
        org_email = current_user.email or (recruiter.company.email if recruiter.company else 'support@careerpearls.com')
        cand_user_id = gattr(gattr(application, 'candidate'), 'user_id')
        cand_email = gattr(gattr(application.candidate, 'user'), 'email') if (application.candidate and application.candidate.user) else ''
        cand_name = gattr(application.candidate, 'full_name') or 'Candidate'
        job_title = application.job.title

        # Update interview status
        interview.status = outcome
        
        # Update application status based on outcome
        if outcome == 'Passed':
            application.status = 'Selected'  # Officially Hired!

            # Read and record offered salary
            salary_offered = (request.form.get('salary_offered') or '').strip()
            if not salary_offered:
                if application.job.salary_range:
                    salary_offered = application.job.salary_range
                elif application.job.salary_min and application.job.salary_max:
                    salary_offered = f"PKR {application.job.salary_min:,} - {application.job.salary_max:,} / month"
                elif application.job.salary_max:
                    salary_offered = f"PKR {application.job.salary_max:,} / month"
                else:
                    salary_offered = "Competitive Package"

            # Create or update Offer record
            offer = Offer.query.filter_by(application_id=application.id).first()
            if not offer:
                offer = Offer(
                    application_id=application.id,
                    salary_offered=salary_offered,
                    status='Accepted'
                )
                db.session.add(offer)
            else:
                offer.salary_offered = salary_offered
                offer.status = 'Accepted'

            flash_msg = f'🎉 Candidate {cand_name} is officially HIRED for {job_title} ({salary_offered})! (Job starting date & offer details dispatched).'
            
            # 1. In-App Message
            if cand_user_id:
                db.session.add(Message(
                    sender_id=current_user.id,
                    receiver_id=cand_user_id,
                    application_id=application.id,
                    body=(
                        f"[{org_name}]\n"
                        f"🎉 Congratulations! You have successfully cleared the interview evaluation and you are officially HIRED for the {job_title} position!\n\n"
                        f"💼 Offered Compensation: {salary_offered}\n\n"
                        f"You will receive your next email within a few days containing your official job starting date, contract, and onboarding paperwork.\n\n"
                        f"Welcome to the team!"
                    )
                ))
                # 2. In-App Notification
                db.session.add(Notification(
                    user_id=cand_user_id,
                    message=f"🎉 Congratulations! You are officially HIRED for {job_title} at {org_name} ({salary_offered})! Job starting date and onboarding details will be sent to your email within a few days.",
                    type='offer'
                ))
            
            # 3. Dispatched Official Hired Email
            if cand_email:
                try:
                    send_candidate_hired_email(
                        candidate_email=cand_email,
                        candidate_name=cand_name,
                        company_name=org_name,
                        job_title=job_title,
                        employer_name=recruiter.name or 'Hiring Manager',
                        company_email=org_email,
                        salary_offered=salary_offered
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to dispatch hired email: {e}")

        elif outcome == 'Failed':
            application.status = 'Rejected'
            final_reason = notes or 'Thank you for coming. We appreciate your time interviewing with us, but have decided to proceed with other candidates.'
            application.rejection_reason = final_reason
            flash_msg = f'Interview outcome recorded: Failed. Application for {cand_name} has been updated to Rejected (Thank you for coming).'
            
            if cand_user_id:
                db.session.add(Message(
                    sender_id=current_user.id,
                    receiver_id=cand_user_id,
                    application_id=application.id,
                    body=(
                        f"[{org_name}]\n"
                        f"Thank you for coming and taking the time to interview with us for the {job_title} position.\n\n"
                        f"We appreciate your effort and interest in our organization, but have decided to move forward with other candidates at this time. We wish you the very best in your career endeavors!"
                    )
                ))
                db.session.add(Notification(
                    user_id=cand_user_id,
                    message=f"Interview Update: Thank you for coming to interview with {org_name} for {job_title}. We appreciate your time and wish you the best!",
                    type='rejection'
                ))
            
            if cand_email:
                try:
                    send_interview_failed_email(
                        candidate_email=cand_email,
                        candidate_name=cand_name,
                        company_name=org_name,
                        job_title=job_title,
                        reason=final_reason,
                        company_email=org_email,
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to dispatch rejection email: {e}")

        elif outcome == 'Rescheduled':
            interview.status = 'Rescheduled'
            application.status = 'Interview Scheduled'
            flash_msg = f'Interview status updated: Rescheduled for {cand_name}. (Candidate will receive rescheduling email soon).'
            
            if cand_user_id:
                db.session.add(Message(
                    sender_id=current_user.id,
                    receiver_id=cand_user_id,
                    application_id=application.id,
                    body=(
                        f"[{org_name}]\n"
                        f"We will be rescheduling your interview for the {job_title} position.\n\n"
                        f"You will receive an email soon with your updated interview schedule and details."
                    )
                ))
                db.session.add(Notification(
                    user_id=cand_user_id,
                    message=f"📅 Interview Update: We are rescheduling your interview for {job_title} with {org_name}. You will receive an email soon with new schedule details.",
                    type='interview'
                ))
            
            if cand_email:
                try:
                    send_interview_rescheduled_email(
                        candidate_email=cand_email,
                        candidate_name=cand_name,
                        company_name=org_name,
                        job_title=job_title,
                        employer_name=recruiter.name or 'Hiring Manager',
                        company_email=org_email,
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to dispatch reschedule email: {e}")
        else:
            application.status = outcome
            flash_msg = f'Interview outcome recorded: {outcome}.'
        
        log_status_change(application, application.status, current_user.id)
        create_audit_log(current_user.id, 'interview_outcome_recorded', 'Interview', interview.id, details=f"Outcome: {outcome}. Notes: {notes}")
        db.session.commit()
        
        safe_flash_success(flash_msg)
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Record interview outcome error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to record interview outcome. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/send-email', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def send_direct_email(app_id):
    """
    Send a direct email from employer to candidate (separate from in-app messaging).
    """
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        subject = (request.form.get('subject') or '').strip()
        message_body = (request.form.get('message_body') or '').strip()

        if not subject or not message_body:
            safe_flash_error('Please provide both subject and message body.')
            return safe_redirect('employer.manage_applications')

        candidate_email = application.candidate.user.email
        candidate_name = application.candidate.full_name
        company_name = recruiter.company.name
        employer_name = recruiter.name or 'Recruiter'

        # Send the direct email
        ok, err = send_direct_employer_email(
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            company_name=company_name,
            employer_name=employer_name,
            subject=subject,
            message_body=message_body,
            job_title=application.job.title,
        )

        if ok:
            # Log the action for audit purposes
            create_audit_log(
                current_user.id, 
                'direct_email_sent', 
                'Application', 
                application.id, 
                details=f"Subject: {subject}"
            )
            
            # Add notification with full clear email details for candidate dashboard
            notif_message = f"✉️ Email: {subject}\n\n{message_body}"
            db.session.add(Notification(
                user_id=application.candidate.user_id,
                message=notif_message,
                type='email',
            ))
            
            db.session.commit()
            safe_flash_success(f'Email sent to {candidate_email}')
        else:
            safe_flash_error(f'Failed to send email: {err}')

        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Send direct email error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to send email. Please try again.')
        return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/resume/<int:resume_id>/delete', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def delete_candidate_resume(app_id, resume_id):
    """
    Allow employer to delete a candidate's uploaded resume from the application view.
    Only permitted if the application belongs to the employer's company.
    """
    try:
        import os
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)

        resume = Resume.query.get_or_404(resume_id)
        # Verify resume belongs to the applicant
        if resume.candidate_id != application.candidate_id:
            abort(403)

        # Delete file from disk if it exists
        try:
            upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
            if upload_folder and resume.file_path:
                file_path = os.path.join(upload_folder, resume.file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            current_app.logger.warning(f"Could not delete resume file: {e}")

        db.session.delete(resume)
        create_audit_log(current_user.id, 'candidate_resume_deleted', 'Resume', resume_id)
        db.session.commit()
        safe_flash_success('Candidate resume deleted successfully.')
        return safe_redirect('employer.manage_applications')
    except Exception as e:
        current_app.logger.error(f"Delete candidate resume error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to delete resume. Please try again.')
        return safe_redirect('employer.manage_applications')



# ---------------------------------------------------------------------------
# My Jobs - Employer's Own Job Listings Management
# ---------------------------------------------------------------------------

@employer_bp.route('/my-jobs')
@login_required
@role_required('employer')
def my_jobs():
    recruiter = get_recruiter_or_403()
    company = recruiter.company
    status_filter = request.args.get('status', '')
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Job.query.filter_by(company_id=company.id)
    if status_filter == 'hired':
        query = query.filter(Job.is_hired == True)
    elif status_filter == 'active':
        query = query.filter(Job.status == 'active', or_(Job.is_hired == False, Job.is_hired.is_(None)))
    elif status_filter == 'paused':
        query = query.filter(Job.status == 'paused')
    elif status_filter == 'unpublished':
        query = query.filter(or_(Job.status == 'unpublished', Job.approval_status == 'unpublished', Job.unpublish_reason.isnot(None)))
    elif status_filter in ('closed', 'deleted'):
        query = query.filter(Job.status == status_filter)

    if q:
        query = query.filter(Job.title.ilike(f'%{q}%'))

    # Order un-hired active jobs at the TOP, hired jobs at the BOTTOM
    jobs = query.order_by(Job.is_hired.asc(), Job.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    status_counts = {
        'all': Job.query.filter_by(company_id=company.id).count(),
        'active': Job.query.filter(Job.company_id == company.id, Job.status == 'active', or_(Job.is_hired == False, Job.is_hired.is_(None))).count(),
        'paused': Job.query.filter_by(company_id=company.id, status='paused').count(),
        'unpublished': Job.query.filter(Job.company_id == company.id, or_(Job.status == 'unpublished', Job.approval_status == 'unpublished', Job.unpublish_reason.isnot(None))).count(),
        'hired': Job.query.filter(Job.company_id == company.id, or_(Job.is_hired == True, Job.status == 'hired')).count(),
    }

    return render_template('employer/my_jobs.html', jobs=jobs, company=company,
                           status_filter=status_filter, status_counts=status_counts, q=q,
                           now=datetime.utcnow())


@employer_bp.route('/jobs/<int:job_id>/toggle-hired', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.my_jobs')
def toggle_job_hired(job_id):
    recruiter = get_recruiter_or_403()
    job = Job.query.get_or_404(job_id)
    if not job_belongs_to_recruiter(job, recruiter):
        abort(403)
    
    # Toggle hired state
    if job.is_hired:
        # Reopen job
        job.is_hired = False
        job.status = 'active'
        db.session.commit()
        safe_flash_success(f"🎉 Job '{job.title}' has been successfully REOPENED! It is now active and visible to candidates.")
    else:
        # Mark as Hired
        job.is_hired = True
        job.status = 'hired'
        db.session.commit()
        safe_flash_success(f"🎉 Job '{job.title}' marked as Hired / Position Filled! It is now hidden from public candidate searches.")
    
    return safe_redirect('employer.my_jobs')


@employer_bp.route('/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def edit_job(job_id):
    recruiter = get_recruiter_or_403()
    job = Job.query.get_or_404(job_id)
    if not job_belongs_to_recruiter(job, recruiter):
        abort(403)

    form = JobPostForm(obj=job)
    form.category_id.choices = [(c.id, c.name) for c in JobCategory.query.order_by(JobCategory.name).all()]

    if form.validate_on_submit():
        if form.closes_at.data and form.closes_at.data < datetime.utcnow():
            flash('Application deadline date cannot be in the past. Please select a future date & time.', 'danger')
            return render_template('employer/edit_job.html', form=form, job=job)
        job.title = form.title.data.strip()
        job.category_id = form.category_id.data
        job.description = form.description.data.strip()
        job.location = form.location.data.strip()
        job.salary_range = (form.salary_range.data or '').strip() or None
        job.employment_type = form.employment_type.data
        job.experience_required = (form.experience_required.data or '').strip() or None
        job.closes_at = form.closes_at.data
        if form.skills.data is not None:
            JobSkill.query.filter_by(job_id=job.id).delete()
            for skill in [s.strip() for s in form.skills.data.split(',') if s.strip()]:
                db.session.add(JobSkill(job_id=job.id, skill_name=skill, is_required=True))
        create_audit_log(current_user.id, 'job_updated', 'Job', job.id)
        db.session.commit()
        flash('Job listing updated successfully!', 'success')
        return redirect(url_for('employer.my_jobs'))

    if request.method == 'GET':
        form.skills.data = ', '.join([s.skill_name for s in job.skills.all()])
    return render_template('employer/edit_job.html', form=form, job=job)


@employer_bp.route('/applications/<int:app_id>/hold', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def hold_application(app_id):
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)
        hold_reason = request.form.get('hold_reason', '').strip()
        application.on_hold = True
        application.hold_reason = hold_reason or 'Placed on hold by employer'
        log_status_change(application, 'On Hold', current_user.id)
        create_audit_log(current_user.id, 'application_placed_on_hold', 'Application', application.id)
        db.session.add(Notification(user_id=application.candidate.user_id,
            message=f'Your application for {application.job.title} has been placed on hold.',
            type='status_update'))
        db.session.commit()
        safe_flash_success('Application placed on hold.')
    except Exception as e:
        current_app.logger.error(f'Hold application error: {e}')
        db.session.rollback()
        safe_flash_error('Failed to place application on hold.')
    return safe_redirect('employer.manage_applications')


@employer_bp.route('/applications/<int:app_id>/resume', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def resume_application(app_id):
    try:
        recruiter = get_recruiter_or_403()
        application = Application.query.get_or_404(app_id)
        if not job_belongs_to_recruiter(application.job, recruiter):
            abort(403)
        application.on_hold = False
        application.hold_reason = None
        log_status_change(application, application.status, current_user.id)
        create_audit_log(current_user.id, 'application_resumed', 'Application', application.id)
        db.session.add(Notification(user_id=application.candidate.user_id,
            message=f'Your application for {application.job.title} has been resumed from hold.',
            type='status_update'))
        db.session.commit()
        safe_flash_success('Application resumed from hold.')
    except Exception as e:
        current_app.logger.error(f'Resume application error: {e}')
        db.session.rollback()
        safe_flash_error('Failed to resume application.')
    return safe_redirect('employer.manage_applications')


@employer_bp.route('/interviews/<int:interview_id>/feedback', methods=['POST'])
@login_required
@role_required('employer')
@safe_button_handler('employer.manage_applications')
def submit_interview_feedback(interview_id):
    try:
        recruiter = get_recruiter_or_403()
        interview = Interview.query.get_or_404(interview_id)
        if not job_belongs_to_recruiter(interview.application.job, recruiter):
            abort(403)
        outcome = request.form.get('outcome', '').strip()
        feedback_text = request.form.get('feedback', '').strip()
        rating = request.form.get('rating', type=int)
        next_action = request.form.get('next_action', '')
        if not outcome:
            safe_flash_error('Please select an outcome.')
            return safe_redirect('employer.manage_applications')
        interview.status = 'Completed' if outcome == 'completed' else 'Cancelled'
        existing = Interviewer.query.filter_by(interview_id=interview.id, user_id=current_user.id).first()
        if not existing:
            existing = Interviewer(interview_id=interview.id, user_id=current_user.id)
            db.session.add(existing)
        if feedback_text:
            existing.feedback = feedback_text
        if rating and 1 <= rating <= 5:
            existing.rating = rating
        application = interview.application
        if outcome == 'completed' and next_action:
            if next_action in ('selected', 'offer'):
                application.status = 'Selected'
                if next_action == 'offer' and not application.offer:
                    db.session.add(Offer(application_id=application.id, status='Pending'))
            elif next_action == 'rejected':
                application.status = 'Rejected'
                application.rejection_reason = feedback_text or 'Interview performance'
            log_status_change(application, application.status, current_user.id)
            db.session.add(Notification(user_id=application.candidate.user_id,
                message=f'Interview result for {application.job.title}: {interview.status}. Application status updated to {application.status}.',
                type='interview_update'))
        create_audit_log(current_user.id, 'interview_feedback_submitted', 'Interview', interview.id)
        db.session.commit()
        safe_flash_success(f'Interview marked {interview.status}. Feedback saved.')
    except Exception as e:
        current_app.logger.error(f'Interview feedback error: {e}')
        db.session.rollback()
        safe_flash_error('Failed to submit feedback.')
    return safe_redirect('employer.manage_applications')


@employer_bp.route('/api/verification-status')
@login_required
@role_required('employer')
def api_verification_status():
    recruiter = get_recruiter_or_403()
    company = recruiter.company
    return jsonify({
        'status': company.verification_status if company else 'Unknown',
        'rejection_reason': company.rejection_reason if company else None,
    })
