from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import Job, JobCategory, Application, SavedJob, can_apply, create_audit_log, ApplicationStatusHistory
from app.utils import role_required, build_filtered_job_query
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional

jobboard_bp = Blueprint('jobboard', __name__, template_folder='templates')


class ApplyForm(FlaskForm):
    cover_letter = TextAreaField('Cover Letter', validators=[Optional()])
    resume_id = SelectField('Resume', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit Application')


@jobboard_bp.route('/')
def job_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '')
    category_id = request.args.get('category', type=int)
    location = request.args.get('location', '')
    employment_type = request.args.get('type', request.args.get('employment_type', ''))
    salary = request.args.get('salary', '')
    sort = request.args.get('sort', 'newest')

    query = Job.query.filter(
        Job.status == 'active',
        or_(Job.approval_status == 'approved', Job.approval_status.is_(None)),
        or_(Job.is_hired == False, Job.is_hired.is_(None)),
    )
    
    query = build_filtered_job_query(
        query=query,
        search=search,
        location=location,
        category=category_id,
        employment_type=employment_type,
        salary=salary
    )
    
    # Filter out expired jobs
    query = query.filter(or_(Job.closes_at.is_(None), Job.closes_at > datetime.utcnow()))

    if sort == 'oldest':
        query = query.order_by(Job.created_at.asc())
    else:
        query = query.order_by(Job.created_at.desc())

    jobs = query.paginate(page=page, per_page=12, error_out=False)
    categories = JobCategory.query.order_by(JobCategory.name).all()

    return render_template(
        'jobboard/job_list.html',
        jobs=jobs,
        categories=categories,
        search=search,
        category_id=category_id,
        location=location,
        employment_type=employment_type,
        salary=salary,
        sort=sort,
    )


@jobboard_bp.route('/<int:job_id>')
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    already_applied = False
    is_saved = False

    if current_user.is_authenticated and current_user.is_candidate():
        candidate = current_user.candidate
        if candidate:
            existing_app = Application.query.filter_by(
                job_id=job.id, candidate_id=candidate.id
            ).first()
            already_applied = existing_app is not None and existing_app.status not in ['Withdrawn', 'Rejected']
            is_saved = SavedJob.query.filter_by(
                candidate_id=candidate.id, job_id=job.id
            ).first() is not None

    return render_template(
        'jobboard/job_detail.html',
        job=job,
        already_applied=already_applied,
        is_saved=is_saved,
        is_open=job.accepts_applications(),
    )


@jobboard_bp.route('/<int:job_id>/apply', methods=['GET', 'POST'])
@login_required
@role_required('candidate')
def apply(job_id):
    job = Job.query.get_or_404(job_id)
    candidate = current_user.candidate

    allowed, message = can_apply(candidate.id, job)
    if not allowed:
        flash(message, 'warning')
        return redirect(url_for('jobboard.job_detail', job_id=job_id))

    form = ApplyForm()
    resumes = candidate.resumes.all()
    form.resume_id.choices = [(r.id, r.file_path) for r in resumes]

    if not resumes:
        flash('Please upload a resume before applying.', 'warning')
        return redirect(url_for('candidate.profile'))

    if form.validate_on_submit():
        existing_app = Application.query.filter_by(job_id=job.id, candidate_id=candidate.id).first()
        if existing_app:
            if existing_app.status not in ['Withdrawn', 'Rejected']:
                flash('You have already applied for this job. You cannot re-apply unless your previous application is withdrawn or rejected by the employer.', 'warning')
                return redirect(url_for('jobboard.job_detail', job_id=job_id))

            old_status = existing_app.status
            existing_app.status = 'Applied'
            existing_app.withdrawn_at = None
            existing_app.rejection_reason = None
            existing_app.resume_id = form.resume_id.data
            existing_app.cover_letter = form.cover_letter.data
            existing_app.applied_at = datetime.utcnow()
            existing_app.updated_at = datetime.utcnow()
            existing_app.is_read_by_employer = False
            existing_app.is_read_by_candidate = True
            application = existing_app
        else:
            old_status = None
            application = Application(
                job_id=job.id,
                candidate_id=candidate.id,
                resume_id=form.resume_id.data,
                cover_letter=form.cover_letter.data,
                status='Applied',
                applied_at=datetime.utcnow(),
                is_read_by_employer=False,
                is_read_by_candidate=True,
            )
            db.session.add(application)
            db.session.flush()

        db.session.add(ApplicationStatusHistory(
            application_id=application.id,
            old_status=old_status,
            new_status='Applied',
            changed_by=current_user.id,
        ))
        create_audit_log(current_user.id, 'application_submitted', 'Application', application.id)
        db.session.commit()
        try:
            from app.email_utils import send_job_application_email
            send_job_application_email(candidate, job)
        except Exception:
            pass
        flash('Application submitted successfully!', 'success')
        return redirect(url_for('candidate.dashboard'))

    return render_template('jobboard/apply.html', form=form, job=job)


@jobboard_bp.route('/<int:job_id>/save', methods=['POST'])
@login_required
@role_required('candidate')
def save_job(job_id):
    job = Job.query.get_or_404(job_id)
    candidate = current_user.candidate
    existing = SavedJob.query.filter_by(candidate_id=candidate.id, job_id=job.id).first()
    if existing:
        flash('Job already saved.', 'info')
    else:
        db.session.add(SavedJob(candidate_id=candidate.id, job_id=job.id))
        db.session.commit()
        flash('Job saved!', 'success')
    return redirect(url_for('jobboard.job_detail', job_id=job_id))
