from datetime import date, datetime

from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, session
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Application, Interview, SavedJob, Job, Resume,
    CandidateInterest, CandidateEducation, CandidateSkill, CandidateCertification,
    Message, Notification,
    CAREER_STATUS_OPTIONS, INTEREST_OPTIONS, WORK_MODE_OPTIONS, PREDEFINED_SKILLS,
    create_audit_log,
)
from app.candidate.forms import (
    ProfileForm, ResumeUploadForm, PhotoUploadForm, EducationForm, SkillForm,
    OnboardingBasicForm, OnboardingCareerForm, OnboardingProfessionalForm,
    OnboardingCredentialsForm, CertificationForm, SocialLinksForm,
)
from app.candidate.onboarding_store import (
    get_draft, update_draft, mark_onboarding_complete,
    is_onboarding_complete, SessionCandidateView,
)
from app.utils import role_required, save_upload, save_base64_image
from app.button_utils import (
    safe_button_handler, safe_get_candidate, safe_flash_success, 
    safe_flash_error, safe_redirect, safe_file_upload, safe_execute_db_operation
)

candidate_bp = Blueprint('candidate', __name__, template_folder='templates')

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
CERTIFICATE_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
ONBOARDING_TOTAL_STEPS = 5


def _testing_mode():
    return current_app.config.get('TESTING_MODE', False)


def _onboarding_done(candidate):
    if _testing_mode():
        return is_onboarding_complete()
    return candidate and candidate.onboarding_complete


def _candidate_view(candidate):
    if _testing_mode():
        return SessionCandidateView()
    return candidate


def _year_to_date(value):
    if value and str(value).strip().isdigit():
        year = int(str(value).strip())
        if 0 <= year <= 99:
            year += 2000
        if 1950 <= year <= 2100:
            return date(year, 1, 1)
    return None


def _split_phone(full_phone):
    if not full_phone:
        return '+92', ''
    parts = full_phone.strip().split(' ', 1)
    if len(parts) == 2 and parts[0].startswith('+'):
        return parts[0], parts[1]
    return '+92', full_phone.strip()


def _apply_social_links(candidate, form):
    candidate.github_url = form.github_url.data.strip() if form.github_url.data else None
    candidate.linkedin_url = form.linkedin_url.data.strip() if form.linkedin_url.data else None
    candidate.kaggle_url = form.kaggle_url.data.strip() if form.kaggle_url.data else None
    candidate.sync_links_to_table()


def _populate_social_links_form(form, candidate):
    form.github_url.data = candidate.github_url or ''
    form.linkedin_url.data = candidate.linkedin_url or ''
    form.kaggle_url.data = candidate.kaggle_url or ''


def _rel_count(rel_or_list):
    if rel_or_list is None:
        return 0
    try:
        if callable(getattr(rel_or_list, 'count', None)):
            try:
                return rel_or_list.count()
            except TypeError:
                pass
    except (AttributeError, TypeError):
        pass
    return len(rel_or_list)


def _profile_completion(view, education_list, skills):
    required_checks = [
        bool(view.full_name),
        bool(view.phone),
        bool(view.location),
        bool(view.headline),
        bool(view.availability),
        bool(view.work_mode),
        view.has_internship is not None,
        bool(view.profile_image),
        _rel_count(education_list) > 0,
        _rel_count(skills) > 0,
    ]
    completed_count = sum(1 for item in required_checks if item)
    return int((completed_count / len(required_checks)) * 100)


def _format_url(url_val):
    if not url_val:
        return None
    val = url_val.strip()
    if not val:
        return None
    if not (val.startswith('http://') or val.startswith('https://')):
        val = 'https://' + val
    return val


def _validate_social_links(form):
    import re
    valid = True

    def _add_error(field, msg):
        current_errors = list(field.errors) if field.errors else []
        current_errors.append(msg)
        field.errors = tuple(current_errors)

    # LinkedIn validation
    if form.linkedin_url.data and form.linkedin_url.data.strip():
        url = _format_url(form.linkedin_url.data)
        if 'linkedin.com' not in url.lower():
            _add_error(form.linkedin_url, 'Please enter a valid LinkedIn URL (e.g. https://linkedin.com/in/username).')
            valid = False
        else:
            form.linkedin_url.data = url

    # GitHub validation
    if form.github_url.data and form.github_url.data.strip():
        url = _format_url(form.github_url.data)
        if 'github.com' not in url.lower():
            _add_error(form.github_url, 'Please enter a valid GitHub URL (e.g. https://github.com/username).')
            valid = False
        else:
            form.github_url.data = url

    # Kaggle validation
    if form.kaggle_url.data and form.kaggle_url.data.strip():
        url = _format_url(form.kaggle_url.data)
        if 'kaggle.com' not in url.lower():
            _add_error(form.kaggle_url, 'Please enter a valid Kaggle URL (e.g. https://kaggle.com/username).')
            valid = False
        else:
            form.kaggle_url.data = url

    # Portfolio validation
    if form.portfolio_url.data and form.portfolio_url.data.strip():
        url = _format_url(form.portfolio_url.data)
        if not re.match(r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$', url):
            _add_error(form.portfolio_url, 'Please enter a valid website URL (e.g. https://myportfolio.com).')
            valid = False
        else:
            form.portfolio_url.data = url

    return valid


def _apply_profile_form(candidate, form):
    candidate.full_name = form.full_name.data.strip()
    c_code = form.country_code.data or '+92'
    raw_phone = form.phone.data.strip() if form.phone.data else ''
    candidate.phone = f"{c_code} {raw_phone}".strip() if raw_phone else None
    candidate.location = form.location.data.strip() if form.location.data else None
    candidate.headline = form.headline.data.strip() if form.headline.data else None
    candidate.availability = form.availability.data.strip() if form.availability.data else None
    candidate.bio = form.bio.data.strip() if form.bio.data else None
    candidate.work_mode = form.work_mode.data or None
    if form.has_internship.data == 'yes':
        candidate.has_internship = True
    elif form.has_internship.data == 'no':
        candidate.has_internship = False
    candidate.internship_details = (
        form.internship_details.data.strip() if form.internship_details.data else None
    )
    candidate.linkedin_url = _format_url(form.linkedin_url.data) if form.linkedin_url.data else None
    candidate.github_url = _format_url(form.github_url.data) if form.github_url.data else None
    candidate.portfolio_url = _format_url(form.portfolio_url.data) if form.portfolio_url.data else None
    candidate.kaggle_url = _format_url(form.kaggle_url.data) if form.kaggle_url.data else None
    candidate.sync_links_to_table()


def _populate_profile_form_from_view(form, view):
    code, p_num = _split_phone(view.phone)
    form.country_code.data = code
    form.full_name.data = view.full_name
    form.phone.data = p_num
    form.location.data = view.location or ''
    form.headline.data = view.headline or ''
    form.availability.data = view.availability or ''
    form.bio.data = view.bio or ''
    form.work_mode.data = view.work_mode or ''
    if view.has_internship is True:
        form.has_internship.data = 'yes'
    elif view.has_internship is False:
        form.has_internship.data = 'no'
    else:
        form.has_internship.data = ''
    form.internship_details.data = view.internship_details or ''
    form.linkedin_url.data = getattr(view, 'linkedin_url', '') or ''
    form.github_url.data = getattr(view, 'github_url', '') or ''
    form.portfolio_url.data = getattr(view, 'portfolio_url', '') or ''
    form.kaggle_url.data = getattr(view, 'kaggle_url', '') or ''


def _populate_profile_form(form, candidate):
    code, p_num = _split_phone(candidate.phone)
    form.country_code.data = code
    form.full_name.data = candidate.full_name
    form.phone.data = p_num
    form.location.data = candidate.location or ''
    form.headline.data = candidate.headline or ''
    form.availability.data = candidate.availability or ''
    form.bio.data = candidate.bio or ''
    form.work_mode.data = candidate.work_mode or ''
    if candidate.has_internship is True:
        form.has_internship.data = 'yes'
    elif candidate.has_internship is False:
        form.has_internship.data = 'no'
    else:
        form.has_internship.data = ''
    form.internship_details.data = candidate.internship_details or ''
    form.linkedin_url.data = candidate.linkedin_url or ''
    form.github_url.data = candidate.github_url or ''
    form.portfolio_url.data = candidate.portfolio_url or ''
    form.kaggle_url.data = candidate.kaggle_url or ''
    form.work_mode.data = candidate.work_mode or ''
    if candidate.has_internship is True:
        form.has_internship.data = 'yes'
    elif candidate.has_internship is False:
        form.has_internship.data = 'no'
    else:
        form.has_internship.data = ''
    form.internship_details.data = candidate.internship_details or ''


def _apply_profile_to_draft(form):
    has_internship = None
    if form.has_internship.data == 'yes':
        has_internship = True
    elif form.has_internship.data == 'no':
        has_internship = False
    update_draft(
        full_name=form.full_name.data.strip(),
        phone=form.phone.data.strip() if form.phone.data else '',
        location=form.location.data.strip() if form.location.data else '',
        headline=form.headline.data.strip() if form.headline.data else '',
        availability=form.availability.data.strip() if form.availability.data else '',
        bio=form.bio.data.strip() if form.bio.data else '',
        work_mode=form.work_mode.data or '',
        has_internship=has_internship,
        internship_details=form.internship_details.data.strip() if form.internship_details.data else '',
    )

ONBOARDING_STEPS = [
    {'num': 1, 'title': 'Basic Info', 'subtitle': 'Your identity and contact details'},
    {'num': 2, 'title': 'Career Status', 'subtitle': 'Tell us where you are in your journey'},
    {'num': 3, 'title': 'Interests', 'subtitle': 'Fields you want to explore or work in'},
    {'num': 4, 'title': 'Professional', 'subtitle': 'Headline and availability for employers'},
    {'num': 5, 'title': 'Credentials', 'subtitle': 'Education, skills, and resume'},
]


def _save_profile_photo(candidate, cropped_data=None, file=None):
    upload_folder = current_app.config['UPLOAD_FOLDER']
    filename = None
    if cropped_data:
        filename = save_base64_image(cropped_data, upload_folder)
    elif file and file.filename:
        filename = save_upload(file, upload_folder, IMAGE_EXTENSIONS)
    if filename:
        candidate.profile_image = filename
        return True
    return False


def _onboarding_context(candidate, step, edit_mode=False):
    view = _candidate_view(candidate)
    draft = get_draft() if _testing_mode() else None
    if draft:
        selected = draft.get('interests', [])
        status = draft.get('career_status', '')
    else:
        selected = [i.interest_name for i in candidate.interests.all()]
        status = candidate.career_status
    return {
        'step': step,
        'total_steps': ONBOARDING_TOTAL_STEPS,
        'steps_meta': ONBOARDING_STEPS,
        'candidate': view,
        'edit_mode': edit_mode,
        'career_options': CAREER_STATUS_OPTIONS,
        'interest_options': INTEREST_OPTIONS,
        'selected_interests': selected,
        'current_status': status,
        'predefined_skills': PREDEFINED_SKILLS,
    }


@candidate_bp.before_request
def candidate_guards():
    if not current_user.is_authenticated:
        return None  # Let Flask-Login handle authentication naturally
    if current_user.needs_oauth_onboarding():
        return redirect(url_for('auth.oauth_onboarding'))
    if current_user.is_candidate():
        candidate = current_user.candidate
        if candidate and not _onboarding_done(candidate):
            # Only force onboarding when trying to access candidate-specific dashboard pages
            allowed = {'candidate.onboarding', 'candidate.profile', 'candidate.deactivate_profile', 'auth.logout', 'static', 'auth.oauth_onboarding'}
            if request.endpoint not in allowed:
                return redirect(url_for('candidate.onboarding'))


@candidate_bp.route('/onboarding', methods=['GET', 'POST'])
@candidate_bp.route('/onboarding/<path:dummy>', methods=['GET', 'POST'])
@login_required
@role_required('candidate')
def onboarding(dummy=None):
    candidate = current_user.candidate
    edit_mode = request.args.get('edit') == '1'

    if _onboarding_done(candidate) and not edit_mode:
        return redirect(url_for('candidate.profile'))

    view = _candidate_view(candidate)
    draft = get_draft() if _testing_mode() else None

    if draft:
        selected_interests = draft.get('interests', [])
        current_status = draft.get('career_status', '')
    else:
        selected_interests = [i.interest_name for i in candidate.interests.all()] if getattr(candidate, 'interests', None) and callable(getattr(candidate.interests, 'all', None)) else []
        current_status = candidate.career_status or ''

    if request.method == 'POST':
        career_status = request.form.get('career_status')
        interests = request.form.getlist('interests')
        primary_skill = request.form.get('primary_skill', '').strip()
        skill_level = request.form.get('primary_skill_level', 'Intermediate')
        resume_file = request.files.get('resume')

        template_ctx = dict(
            candidate=view,
            career_options=CAREER_STATUS_OPTIONS,
            interest_options=INTEREST_OPTIONS,
            selected_interests=interests,
            current_status=career_status or '',
            edit_mode=edit_mode,
            primary_skill=primary_skill,
            skill_level=skill_level,
            predefined_skills=PREDEFINED_SKILLS,
        )

        if not career_status:
            flash('Please select your career status.', 'warning')
            return render_template('candidate/onboarding.html', **template_ctx)

        if len(interests) < 3:
            flash('Please select at least 3 fields you are interested in.', 'warning')
            return render_template('candidate/onboarding.html', **template_ctx)

        if not primary_skill:
            flash('Please add at least one key technical skill.', 'warning')
            return render_template('candidate/onboarding.html', **template_ctx)

        if _testing_mode():
            update_draft(career_status=career_status, interests=interests)
            draft = get_draft()
            skills = draft.get('skills', [])
            skills.append({'skill_name': primary_skill, 'proficiency_level': skill_level})
            update_draft(skills=skills)
            if resume_file and resume_file.filename:
                filename = save_upload(
                    resume_file,
                    current_app.config['UPLOAD_FOLDER'],
                    CERTIFICATE_EXTENSIONS,
                )
                if filename:
                    draft.setdefault('resumes', []).append({'file_path': filename, 'is_primary': True})
                    update_draft(resumes=draft['resumes'])
            mark_onboarding_complete()
        else:
            candidate.career_status = career_status
            if getattr(candidate, 'interests', None) is not None:
                candidate.interests.delete()
                for name in interests:
                    db.session.add(CandidateInterest(candidate_id=candidate.id, interest_name=name))
            existing_skill = CandidateSkill.query.filter_by(
                candidate_id=candidate.id, skill_name=primary_skill,
            ).first()
            if not existing_skill:
                db.session.add(CandidateSkill(
                    candidate_id=candidate.id,
                    skill_name=primary_skill,
                    proficiency_level=skill_level,
                ))
            if resume_file and resume_file.filename:
                resume_file.seek(0, 2)
                r_size = resume_file.tell()
                resume_file.seek(0)
                if r_size <= 15 * 1024 * 1024:
                    filename = save_upload(
                        resume_file,
                        current_app.config['UPLOAD_FOLDER'],
                        CERTIFICATE_EXTENSIONS,
                    )
                    if filename:
                        is_first = candidate.resumes.count() == 0
                        db.session.add(Resume(
                            candidate_id=candidate.id,
                            file_path=filename,
                            is_primary=is_first,
                        ))
            candidate.onboarding_complete = True
            db.session.commit()

        flash('Profile setup completed! Manage all your details anytime from your profile.', 'success')
        return redirect(url_for('candidate.profile'))

    return render_template(
        'candidate/onboarding.html',
        candidate=view,
        career_options=CAREER_STATUS_OPTIONS,
        interest_options=INTEREST_OPTIONS,
        selected_interests=selected_interests,
        current_status=current_status,
        edit_mode=edit_mode,
        primary_skill='',
        skill_level='Intermediate',
        predefined_skills=PREDEFINED_SKILLS,
    )


@candidate_bp.route('/dashboard')
@login_required
@role_required('candidate')
def dashboard():
    candidate = current_user.candidate
    # Mark candidate unread application status updates as read when viewing dashboard
    if candidate:
        Application.query.filter(
            Application.candidate_id == candidate.id,
            Application.is_read_by_candidate == False
        ).update({'is_read_by_candidate': True}, synchronize_session=False)
        db.session.commit()

    # Exclude withdrawn applications so candidate view is cleanly kept to active applications
    applications = Application.query.filter_by(candidate_id=candidate.id).filter(
        Application.status != 'Withdrawn'
    ).order_by(
        Application.applied_at.desc()
    ).options(
        joinedload(Application.job).joinedload(Job.company)
    ).all()

    apps_by_status = {}
    for status in ['Applied', 'Under Review', 'Screening', 'Shortlisted', 'Interview Scheduled', 'Contacted', 'Selected', 'Rejected']:
        apps_by_status[status] = [a for a in applications if a.status == status]

    # Hired (Selected) apps — show green banner; exclude their interviews from "Upcoming Interviews"
    hired_apps = [a for a in applications if a.status == 'Selected']
    hired_app_ids = {a.id for a in hired_apps}

    # Upcoming interviews — exclude interviews for hired jobs; only show for non-hired (Shortlisted / Interview Scheduled / Under Review)
    from sqlalchemy import not_
    interview_query = (
        Interview.query.join(Application)
        .filter(
            Application.candidate_id == candidate.id,
            Interview.status == 'Scheduled',
        )
    )
    if hired_app_ids:
        interview_query = interview_query.filter(not_(Application.id.in_(hired_app_ids)))
    upcoming_interviews = interview_query.order_by(Interview.scheduled_at.asc()).limit(10).all()

    # Get recent messages
    from sqlalchemy import or_
    try:
        recent_messages = (
            Message.query.filter(
                or_(Message.sender_id == current_user.id, Message.receiver_id == current_user.id)
            )
            .order_by(Message.sent_at.desc())
            .limit(10)
            .all()
        )

        # Count unread messages
        unread_count = (
            Message.query.filter(
                Message.receiver_id == current_user.id,
                Message.is_read == False
            ).count()
        )
    except Exception as e:
        current_app.logger.error(f"Error fetching messages: {e}")
        recent_messages = []
        unread_count = 0

    saved_count = SavedJob.query.filter_by(candidate_id=candidate.id).count()
    total_apps = len(applications)
    interview_count = sum(1 for a in applications if a.status in ('Interview', 'Shortlisted', 'Selected'))
    conversion_rate = round((interview_count / total_apps * 100), 1) if total_apps else 0

    view = _candidate_view(candidate)
    completion_pct = view.calculate_completion_pct() if callable(getattr(view, 'calculate_completion_pct', None)) else candidate.calculate_completion_pct()

    return render_template(
        'candidate/dashboard.html',
        candidate=view,
        completion_pct=completion_pct,
        apps_by_status=apps_by_status,
        hired_apps=hired_apps,
        is_hired=len(hired_apps) > 0,
        upcoming_interviews=upcoming_interviews,
        recent_messages=recent_messages,
        unread_count=unread_count,
        saved_count=saved_count,
        total_apps=total_apps,
        conversion_rate=conversion_rate,
    )


@candidate_bp.route('/messages/<int:application_id>/reply', methods=['POST'])
@login_required
@role_required('candidate')
@safe_button_handler('candidate.dashboard')
def reply_to_message(application_id):
    """
    Allow candidates to reply to employer messages for a specific application.
    """
    try:
        candidate = current_user.candidate
        application = Application.query.get_or_404(application_id)
        
        # Verify application belongs to candidate
        if application.candidate_id != candidate.id:
            safe_flash_error('You can only reply to messages for your own applications.')
            return safe_redirect('candidate.dashboard')
        
        body = (request.form.get('message') or '').strip()
        if not body:
            safe_flash_error('Please enter a message to send.')
            return safe_redirect('candidate.dashboard')
        
        # Find the employer user who sent the last message
        last_message = (
            Message.query.filter_by(application_id=application_id)
            .order_by(Message.sent_at.desc())
            .first()
        )
        
        if not last_message:
            safe_flash_error('No existing conversation found for this application.')
            return safe_redirect('candidate.dashboard')
        
        # Determine recipient (employer)
        employer_user_id = last_message.sender_id if last_message.receiver_id == current_user.id else last_message.receiver_id
        
        # Send reply message
        db.session.add(Message(
            sender_id=current_user.id,
            receiver_id=employer_user_id,
            application_id=application_id,
            body=body,
        ))
        
        # Mark message as read for the candidate
        for msg in Message.query.filter_by(application_id=application_id, receiver_id=current_user.id, is_read=False).all():
            msg.is_read = True
        
        # Notify employer
        db.session.add(Notification(
            user_id=employer_user_id,
            message=f"New reply from {candidate.full_name} regarding your application for {application.job.title}.",
            type='message',
        ))
        
        create_audit_log(current_user.id, 'message_replied', 'Application', application_id)
        db.session.commit()
        
        safe_flash_success('Your reply has been sent to the employer.')
        return safe_redirect('candidate.dashboard')
    except Exception as e:
        current_app.logger.error(f"Reply to message error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to send reply. Please try again.')
        return safe_redirect('candidate.dashboard')


@candidate_bp.route('/messages/<int:message_id>/mark-read', methods=['POST'])
@login_required
@role_required('candidate')
def mark_message_read(message_id):
    """
    Mark a message as read by the candidate.
    """
    try:
        message = Message.query.get_or_404(message_id)
        if message.receiver_id != current_user.id:
            abort(403)
        
        message.is_read = True
        db.session.commit()
        return '', 204
    except Exception as e:
        current_app.logger.error(f"Mark message read error: {e}")
        db.session.rollback()
        return '', 500


@candidate_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('candidate')
@safe_button_handler('candidate.profile')
def profile():
    try:
        candidate = current_user.candidate
    except (AttributeError, Exception):
        candidate = safe_get_candidate()
    
    view = _candidate_view(candidate)
    form = ProfileForm()
    if request.method == 'GET':
        if _testing_mode():
            _populate_profile_form_from_view(form, view)
        else:
            try:
                _populate_profile_form(form, candidate)
            except (AttributeError, Exception):
                _populate_profile_form_from_view(form, view)
    
    photo_form = PhotoUploadForm()
    resume_form = ResumeUploadForm()
    education_form = EducationForm()
    skill_form = SkillForm()
    work_mode_labels = dict(WORK_MODE_OPTIONS)

    if request.form.get('form_type') == 'career_preferences':
        career_status = request.form.get('career_status')
        interests = request.form.getlist('interests')
        if not career_status:
            flash('Please select your career status.', 'warning')
            return redirect(url_for('candidate.profile', _anchor='careerPreferencesSection'))
        if len(interests) < 3:
            flash('Please select at least 3 fields of interest.', 'warning')
            return redirect(url_for('candidate.profile', _anchor='careerPreferencesSection'))
        if _testing_mode():
            update_draft(career_status=career_status, interests=interests)
        else:
            candidate.career_status = career_status
            candidate.interests.delete()
            for name in interests:
                db.session.add(CandidateInterest(candidate_id=candidate.id, interest_name=name))
            db.session.commit()
        flash('Career preferences updated.', 'success')
        return redirect(url_for('candidate.profile', _anchor='careerPreferencesSection'))

    if request.form.get('form_type') == 'photo':
        cropped = request.form.get('cropped_image')
        file = request.files.get('photo')
        if cropped or (file and file.filename):
            if _testing_mode():
                filename = None
                if cropped:
                    filename = save_base64_image(cropped, current_app.config['UPLOAD_FOLDER'])
                elif file and file.filename:
                    filename = safe_file_upload(file, IMAGE_EXTENSIONS, current_app.config['UPLOAD_FOLDER'])
                if filename:
                    update_draft(profile_image=filename)
                    safe_flash_success('Profile photo updated.')
                else:
                    safe_flash_error('Invalid image. Use PNG, JPG, or WEBP.')
            else:
                try:
                    if _save_profile_photo(candidate, cropped_data=cropped, file=file):
                        db.session.commit()
                        safe_flash_success('Profile photo updated.')
                    else:
                        safe_flash_error('Invalid image. Use PNG, JPG, or WEBP.')
                except Exception as e:
                    current_app.logger.error(f"Profile photo upload error: {e}")
                    db.session.rollback()
                    safe_flash_error('Failed to upload profile photo. Please try again.')
        else:
            safe_flash_error('Please choose a photo to upload.')
        return safe_redirect('candidate.profile')

    if 'resume' in request.files and request.files['resume'].filename:
        resume_file = request.files['resume']
        resume_file.seek(0, 2)
        r_size = resume_file.tell()
        resume_file.seek(0)
        if r_size > 15 * 1024 * 1024:
            safe_flash_error('Resume file size exceeds the maximum 15MB limit.')
            return safe_redirect('candidate.profile')

        filename = safe_file_upload(
            resume_file,
            CERTIFICATE_EXTENSIONS,
            current_app.config['UPLOAD_FOLDER'],
        )
        if filename:
            if _testing_mode():
                draft = get_draft()
                is_first = len(draft.get('resumes', [])) == 0
                draft.setdefault('resumes', []).append({
                    'file_path': filename,
                    'is_primary': is_first,
                })
                update_draft(resumes=draft['resumes'])
                safe_flash_success('Resume uploaded successfully.')
            else:
                try:
                    is_first = candidate.resumes.count() == 0
                    db.session.add(Resume(candidate_id=candidate.id, file_path=filename, is_primary=is_first))
                    db.session.commit()
                    safe_flash_success('Resume uploaded successfully.')
                except Exception as e:
                    current_app.logger.error(f"Resume upload error: {e}")
                    db.session.rollback()
                    safe_flash_error('Failed to upload resume. Please try again.')
        else:
            safe_flash_error('Invalid resume file format. Only PDF, JPEG, and PNG files are accepted (max 15MB).')
        return safe_redirect('candidate.profile')

    # Handling Certification Add Form
    cert_form = CertificationForm()
    if request.form.get('cert_form'):
        if not cert_form.validate_on_submit():
            for field, errors in cert_form.errors.items():
                for error in errors:
                    flash(f"{error}", "danger")
            return redirect(url_for('candidate.profile', _anchor='certificationsSection'))

        cert_file = request.files.get('certificate_file')
        if not cert_file or not cert_file.filename:
            flash('Please upload a certificate document file (PDF, JPEG, or PNG) to add this certification.', 'danger')
            return redirect(url_for('candidate.profile', _anchor='certificationsSection'))

        cert_file.seek(0, 2)
        c_size = cert_file.tell()
        cert_file.seek(0)
        if c_size > 25 * 1024 * 1024:
            flash('Certificate file size exceeds the maximum 25MB limit.', 'danger')
            return redirect(url_for('candidate.profile', _anchor='certificationsSection'))

        cert_filename = save_upload(
            cert_file,
            current_app.config['UPLOAD_FOLDER'],
            CERTIFICATE_EXTENSIONS,
        )
        if not cert_filename:
            flash('Invalid certificate format. Only PDF, JPEG, and PNG files are accepted (max 25MB).', 'danger')
            return redirect(url_for('candidate.profile', _anchor='certificationsSection'))

        if _testing_mode():
            draft = get_draft()
            certs = draft.get('certifications', [])
            certs.append({
                'title': cert_form.title.data.strip(),
                'issuing_organization': cert_form.issuing_organization.data.strip(),
                'issue_year': cert_form.issue_year.data.strip() if cert_form.issue_year.data else '',
                'credential_id': cert_form.credential_id.data.strip() if cert_form.credential_id.data else '',
                'credential_url': cert_form.credential_url.data.strip() if cert_form.credential_url.data else '',
                'description': cert_form.description.data.strip() if cert_form.description.data else '',
                'file_path': cert_filename or '',
            })
            update_draft(certifications=certs)
        else:
            db.session.add(CandidateCertification(
                candidate_id=candidate.id,
                title=cert_form.title.data.strip(),
                issuing_organization=cert_form.issuing_organization.data.strip(),
                issue_year=cert_form.issue_year.data.strip() if cert_form.issue_year.data else None,
                credential_id=cert_form.credential_id.data.strip() if cert_form.credential_id.data else None,
                credential_url=cert_form.credential_url.data.strip() if cert_form.credential_url.data else None,
                description=cert_form.description.data.strip() if cert_form.description.data else None,
                file_path=cert_filename,
            ))
            db.session.commit()
        flash('Certification added successfully.', 'success')
        return redirect(url_for('candidate.profile', _anchor='certificationsSection'))

    if request.form.get('institution') and education_form.validate_on_submit():
        start_d = _year_to_date(education_form.start_year.data)
        end_d = _year_to_date(education_form.end_year.data)
        is_cur = bool(education_form.is_current.data) or (end_d is None) or (end_d is not None and end_d.year >= datetime.utcnow().year)
        if _testing_mode():
            draft = get_draft()
            edu_list = draft.get('education', [])
            edu_list.append({
                'institution': education_form.institution.data.strip(),
                'degree': education_form.degree.data.strip(),
                'field_of_study': education_form.field_of_study.data.strip() or '',
                'is_current': is_cur,
                'start_date': start_d,
                'end_date': end_d,
            })
            update_draft(education=edu_list)
        else:
            db.session.add(CandidateEducation(
                candidate_id=candidate.id,
                institution=education_form.institution.data.strip(),
                degree=education_form.degree.data.strip(),
                field_of_study=education_form.field_of_study.data.strip() or None,
                is_current=is_cur,
                start_date=start_d,
                end_date=end_d,
            ))
            db.session.commit()
        flash('Education added.', 'success')
        return redirect(url_for('candidate.profile', _anchor='educationSection'))

    if request.form.get('skill_name') and skill_form.validate_on_submit():
        s_name = skill_form.skill_name.data.strip()
        s_level = skill_form.proficiency_level.data
        if _testing_mode():
            draft = get_draft()
            skills = draft.get('skills', [])
            new_id = len(skills) + 1
            skills.append({
                'id': new_id,
                'skill_name': s_name,
                'proficiency_level': s_level,
            })
            update_draft(skills=skills)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import jsonify
                return jsonify({'success': True, 'skill': {'id': new_id, 'skill_name': s_name, 'proficiency_level': s_level}})
        else:
            new_skill = CandidateSkill(
                candidate_id=candidate.id,
                skill_name=s_name,
                proficiency_level=s_level,
            )
            db.session.add(new_skill)
            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import jsonify
                return jsonify({'success': True, 'skill': {'id': new_skill.id, 'skill_name': new_skill.skill_name, 'proficiency_level': new_skill.proficiency_level}})
        flash('Skill added.', 'success')
        return redirect(url_for('candidate.profile', _anchor='skillsSection'))

    if request.form.get('full_name_submit'):
        social_valid = _validate_social_links(form)
        if form.validate_on_submit() and social_valid:
            try:
                if _testing_mode():
                    _apply_profile_to_draft(form)
                    safe_flash_success('Profile changes saved successfully.')
                else:
                    _apply_profile_form(candidate, form)
                    db.session.commit()
                    safe_flash_success('Profile changes saved successfully.')
            except Exception as e:
                current_app.logger.error(f"Profile update error: {e}")
                db.session.rollback()
                safe_flash_error('Failed to save profile changes. Please try again.')
            return safe_redirect('candidate.profile')

    education = view.education if _testing_mode() else candidate.education.all()
    if _testing_mode():
        education_list = education
        current_education = next((e for e in education_list if e.is_current), None)
        skills = view.skills
        interests = view.interests
        resumes = view.resumes
        certifications = view.certifications
    else:
        education_list = education
        current_education = next((e for e in education_list if e.is_current), None)
        skills = candidate.skills.all()
        interests = candidate.interests.all()
        resumes = candidate.resumes.order_by(Resume.uploaded_at.desc()).all()
        certifications = candidate.certifications.order_by(CandidateCertification.created_at.desc()).all()

    # Calculate Profile Completion Percentage dynamically
    completion_pct = view.calculate_completion_pct() if callable(getattr(view, 'calculate_completion_pct', None)) else candidate.calculate_completion_pct()

    return render_template(
        'candidate/profile.html',
        form=form, photo_form=photo_form, resume_form=resume_form,
        education_form=education_form, skill_form=skill_form, cert_form=cert_form,
        candidate=view, resumes=resumes,
        education=education_list, current_education=current_education,
        skills=skills, interests=interests, certifications=certifications,
        work_mode_labels=work_mode_labels,
        predefined_skills=PREDEFINED_SKILLS,
        career_options=CAREER_STATUS_OPTIONS,
        interest_options=INTEREST_OPTIONS,
        completion_pct=completion_pct,
    )


@candidate_bp.route('/profile/education/<int:edu_id>/delete', methods=['POST'])
@login_required
@role_required('candidate')
@safe_button_handler('candidate.profile')
def delete_education(edu_id):
    try:
        edu = CandidateEducation.query.filter_by(id=edu_id, candidate_id=current_user.candidate.id).first_or_404()
        db.session.delete(edu)
        db.session.commit()
        safe_flash_success('Education removed.')
    except Exception as e:
        current_app.logger.error(f"Delete education error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to remove education. Please try again.')
    return safe_redirect('candidate.profile')


@candidate_bp.route('/profile/skill/<int:skill_id>/delete', methods=['POST'])
@login_required
@role_required('candidate')
@safe_button_handler('candidate.profile')
def delete_skill(skill_id):
    try:
        if _testing_mode():
            draft = get_draft()
            skills = [s for s in draft.get('skills', []) if s.get('id') != skill_id]
            update_draft(skills=skills)
        else:
            skill = CandidateSkill.query.filter_by(id=skill_id, candidate_id=current_user.candidate.id).first_or_404()
            db.session.delete(skill)
            db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({'success': True})
        safe_flash_success('Skill removed.')
    except Exception as e:
        current_app.logger.error(f"Delete skill error: {e}")
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({'success': False, 'error': str(e)}), 400
        safe_flash_error('Failed to remove skill. Please try again.')
    return safe_redirect('candidate.profile')


@candidate_bp.route('/profile/certification/<int:cert_id>/delete', methods=['POST'])
@login_required
@role_required('candidate')
def delete_certification(cert_id):
    if _testing_mode():
        draft = get_draft()
        certs = draft.get('certifications', [])
        if 0 <= cert_id < len(certs):
            certs.pop(cert_id)
            update_draft(certifications=certs)
        flash('Certification removed.', 'info')
        return redirect(url_for('candidate.profile'))
    cert = CandidateCertification.query.filter_by(id=cert_id, candidate_id=current_user.candidate.id).first_or_404()
    db.session.delete(cert)
    db.session.commit()
    flash('Certification removed.', 'info')
    return redirect(url_for('candidate.profile'))


@candidate_bp.route('/saved-jobs')
@login_required
@role_required('candidate')
def saved_jobs():
    candidate = current_user.candidate
    page = request.args.get('page', 1, type=int)
    saved = SavedJob.query.filter_by(candidate_id=candidate.id).order_by(
        SavedJob.saved_at.desc()
    ).options(
        joinedload(SavedJob.job).joinedload(Job.company)
    ).paginate(page=page, per_page=10, error_out=False)
    return render_template('candidate/saved_jobs.html', saved=saved)


@candidate_bp.route('/saved-jobs/<int:job_id>/remove', methods=['POST'])
@login_required
@role_required('candidate')
@safe_button_handler('candidate.saved_jobs')
def remove_saved_job(job_id):
    try:
        saved = SavedJob.query.filter_by(
            candidate_id=current_user.candidate.id, job_id=job_id
        ).first_or_404()
        db.session.delete(saved)
        db.session.commit()
        safe_flash_success('Job removed from saved list.')
    except Exception as e:
        current_app.logger.error(f"Remove saved job error: {e}")
        db.session.rollback()
        safe_flash_error('Failed to remove job. Please try again.')
    return safe_redirect('candidate.saved_jobs')


@candidate_bp.route('/deactivate-profile', methods=['POST'])
@login_required
@role_required('candidate')
@safe_button_handler('candidate.profile')
def deactivate_profile():
    try:
        from app.utils import permanently_delete_user_account
        reason = request.form.get('reason')
        password = request.form.get('password')
        
        if not reason:
            safe_flash_error('Please select a reason for deactivation.')
            return safe_redirect('candidate.profile')
        
        if current_user.password_hash:
            if not password or not current_user.check_password(password):
                safe_flash_error('Incorrect password. Account deactivation cancelled.')
                return safe_redirect('candidate.profile')
        else:
            # Google OAuth user confirmation check
            if not password or password.strip().lower() != current_user.email.strip().lower():
                safe_flash_error('Since you use Google Auth, please enter your email address to confirm deactivation.')
                return safe_redirect('candidate.profile')
        
        user_id = current_user.id
        ok, msg = permanently_delete_user_account(user_id)
        if not ok:
            safe_flash_error('Failed to completely delete account records.')
            return safe_redirect('candidate.profile')
            
        logout_user()
        session.clear()
        safe_flash_success('Account deactivated successfully. Your profile and all data have been completely removed from CareerPearls.')
        return safe_redirect('auth.login', role='candidate')
    except Exception as e:
        current_app.logger.error(f"Deactivate profile error: {e}", exc_info=True)
        db.session.rollback()
        safe_flash_error('Failed to deactivate profile. Please try again.')
        return safe_redirect('candidate.profile')


from app.extensions import csrf

@candidate_bp.route('/application/<int:app_id>/withdraw', methods=['POST'])
@login_required
@role_required('candidate')
@csrf.exempt
def withdraw_application(app_id):
    try:
        candidate = current_user.candidate
        application = Application.query.filter_by(id=app_id, candidate_id=candidate.id).first_or_404()

        if application.status in ['Selected', 'Rejected']:
            safe_flash_error(f'Cannot withdraw an application with status "{application.status}".')
            return redirect(url_for('candidate.dashboard'))

        job_title = application.job.title if application.job else 'Job'
        company_name = application.job.company.name if (application.job and application.job.company) else 'Employer'

        # Update application status to Withdrawn with timestamp
        application.status = 'Withdrawn'
        application.withdrawn_at = datetime.utcnow()

        # Audit log & notify employer
        create_audit_log(current_user.id, 'application_withdrawn', 'Application', application.id)
        try:
            if application.job and application.job.company:
                for rec in application.job.company.recruiters:
                    if rec.user_id:
                        db.session.add(Notification(
                            user_id=rec.user_id,
                            message=f"{candidate.full_name or 'A candidate'} has withdrawn their application for {job_title}.",
                            type='application_withdrawn'
                        ))
        except Exception as e:
            current_app.logger.warning(f"Could not notify recruiter for withdrawal: {e}")

        db.session.commit()
        try:
            from app.email_utils import send_job_withdrawal_email
            if application.job:
                send_job_withdrawal_email(candidate, application.job)
        except Exception as mail_err:
            current_app.logger.warning(f"Could not send withdrawal email: {mail_err}")

        safe_flash_success(f'Your application for "{job_title}" at {company_name} has been withdrawn successfully.')
        return redirect(url_for('candidate.dashboard'))
    except Exception as e:
        current_app.logger.error(f"Withdraw application error: {e}", exc_info=True)
        db.session.rollback()
        safe_flash_error('Could not process withdrawal. Please try again.')
        return redirect(url_for('candidate.dashboard'))


@candidate_bp.route('/toggle-job-notifier', methods=['POST'])
@login_required
@role_required('candidate')
@csrf.exempt
def toggle_job_notifier():
    try:
        from flask import jsonify
        candidate = current_user.candidate
        if not candidate:
            return jsonify({'success': False, 'message': 'Candidate profile not found.'}), 404
        
        data = request.get_json(silent=True) or {}
        if 'enabled' in data:
            candidate.job_notifier_enabled = bool(data['enabled'])
        elif 'enabled' in request.form:
            candidate.job_notifier_enabled = request.form.get('enabled') in ('1', 'true', 'True', 'on')
        else:
            candidate.job_notifier_enabled = not candidate.job_notifier_enabled

        db.session.commit()
        return jsonify({
            'success': True,
            'enabled': candidate.job_notifier_enabled,
            'email': current_user.email,
            'message': f"Job Notifier {'enabled' if candidate.job_notifier_enabled else 'disabled'} for {current_user.email}."
        })
    except Exception as e:
        db.session.rollback()
        from flask import jsonify
        return jsonify({'success': False, 'message': str(e)}), 500
