import base64 # Used for encoding and decoding of data in best format
import os
import re
import uuid
from functools import wraps # Used for manage and modify functions
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename


def get_or_create_user(email, defaults=None, update=None):
    """Safely fetch or create a user by email; handles concurrent insert races."""
    from app.extensions import db
    from app.models import User

    email = email.lower().strip()
    user = User.query.filter_by(email=email).first()
    if user:
        if update:
            for key, value in update.items():
                setattr(user, key, value)
            db.session.commit()
        return user, False

    payload = {'email': email}
    if defaults:
        payload.update(defaults)
    user = User(**payload)
    db.session.add(user)
    try:
        db.session.commit()
        return user, True
    except IntegrityError:
        db.session.rollback()
        user = User.query.filter_by(email=email).first()
        if not user:
            raise
        if update:
            for key, value in update.items():
                setattr(user, key, value)
            db.session.commit()
        return user, False


def get_current_admin():
    """Return authenticated admin user.

    Priority order:
    1. Request-scoped cache (g.admin_user) — fastest path.
    2. Dedicated admin session key (session['admin_user_id']) — set by admin login form.
    3. Flask-Login current_user with role='admin' — allows test-suite compatibility
       and browser sessions where the admin logged in via the main /login route.
       When found via this path, the dedicated key is written immediately so
       subsequent requests use path #2 (no repeated Flask-Login lookups).

    Tab isolation is preserved in practice because:
    - The admin login page (/portal-control-x99/login) writes session['admin_user_id'].
    - Regular candidate/employer logins do NOT set that key.
    - Only users with role='admin' can pass through this function successfully.
    """
    from flask import session, g
    from app.models import User
    from flask_login import current_user as _cu

    if hasattr(g, 'admin_user') and g.admin_user:
        return g.admin_user

    # 1. Dedicated admin session key (set by admin login form)
    admin_id = session.get('admin_user_id')
    if admin_id:
        admin = User.query.get(admin_id)
        if admin and admin.role == 'admin' and admin.is_active:
            g.admin_user = admin
            return admin
        # Stale id — clear it
        session.pop('admin_user_id', None)

    # 2. Flask-Login fallback (for test-suite & backward compatibility)
    try:
        if _cu.is_authenticated and _cu.role == 'admin' and _cu.is_active:
            # Promote to dedicated key so future requests use path #1
            session['admin_user_id'] = _cu.id
            g.admin_user = _cu
            return _cu
    except Exception:
        pass

    return None


def admin_required(f):
    """Restrict admin routes to authenticated admin users (supports dedicated admin session)."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        admin = get_current_admin()
        if not admin:
            flash('Access denied. Super Admin privileges required.', 'danger')
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return wrapped


def role_required(*roles):
    """Decorator enforcing role-based access control."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_upload(file, upload_folder, allowed_extensions):
    if file and allowed_file(file.filename, allowed_extensions):
        ext = file.filename.rsplit('.', 1)[1].lower()
        raw_name = secure_filename(file.filename.rsplit('.', 1)[0])
        if not raw_name:
            raw_name = 'document'
        filename = f"{uuid.uuid4().hex[:8]}_{raw_name}.{ext}"
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        return filename
    return None


def save_base64_image(data_url, upload_folder):
    if not data_url:
        return None
    match = re.match(
        r'data:image/(?P<ext>png|jpe?g|webp);base64,(?P<data>[A-Za-z0-9+/=\s]+)',
        data_url.strip(),
    )
    if not match:
        return None
    ext = match.group('ext').lower()
    if ext == 'jpeg':
        ext = 'jpg'
    try:
        raw = base64.b64decode(match.group('data'))
    except (ValueError, TypeError):
        return None
    if not raw:
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    with open(filepath, 'wb') as handle:
        handle.write(raw)
    return filename


def get_recruiter_or_403():
    from app.safe import ensure_recruiter_profile
    recruiter = ensure_recruiter_profile(current_user)
    if not recruiter:
        abort(403)
    return recruiter


def job_belongs_to_recruiter(job, recruiter):
    return job.company_id == recruiter.company_id


def permanently_delete_user_account(user_id):
    """
    Permanently and completely removes a user account (Candidate or Employer)
    and all associated database records across all tables in Supabase.
    Removes physical file uploads and allows the email or Google OAuth ID
    to be cleanly reused for any role immediately.
    """
    import os
    from flask import current_app
    from app.extensions import db
    from app.models import (
        User, Candidate, CandidateSkill, CandidateInterest, CandidateLink,
        CandidateEducation, CandidateExperience, CandidateCertification, Resume,
        Recruiter, Company, CompanyHiringField, CompanyEmploymentType,
        Job, JobSkill, Application, ApplicationStatusHistory, ApplicationDocument,
        Interview, Interviewer, Offer, SavedJob, Shortlist, Notification,
        Message, Complaint, AuditLog, EmailVerification, AiChatMessage
    )

    def _safe_remove_file(file_path):
        if not file_path or not isinstance(file_path, str):
            return
        if file_path.startswith(('http://', 'https://')):
            return
        try:
            full_path = file_path
            if not os.path.isabs(full_path):
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                full_path = os.path.join(upload_folder, file_path.lstrip('/\\'))
            if os.path.exists(full_path) and os.path.isfile(full_path):
                os.remove(full_path)
        except Exception as e:
            current_app.logger.warning(f"Failed to remove physical file {file_path}: {e}")

    try:
        user = User.query.get(user_id)
        if not user:
            return False, "User not found."

        user_email = user.email.lower().strip() if user.email else None

        # 1. Candidate Cascade
        candidate = getattr(user, 'candidate', None)
        if candidate:
            cid = candidate.id

            # Physical file cleanup for candidate
            _safe_remove_file(getattr(candidate, 'profile_image', None))
            _safe_remove_file(getattr(candidate, 'profile_photo_path', None))

            for cert in CandidateCertification.query.filter_by(candidate_id=cid).all():
                _safe_remove_file(cert.file_path)

            for res in Resume.query.filter_by(candidate_id=cid).all():
                _safe_remove_file(res.file_path)

            CandidateSkill.query.filter_by(candidate_id=cid).delete()
            CandidateInterest.query.filter_by(candidate_id=cid).delete()
            CandidateLink.query.filter_by(candidate_id=cid).delete()
            CandidateEducation.query.filter_by(candidate_id=cid).delete()
            CandidateExperience.query.filter_by(candidate_id=cid).delete()
            CandidateCertification.query.filter_by(candidate_id=cid).delete()
            Resume.query.filter_by(candidate_id=cid).delete()
            SavedJob.query.filter_by(candidate_id=cid).delete()

            for app in Application.query.filter_by(candidate_id=cid).all():
                for doc in ApplicationDocument.query.filter_by(application_id=app.id).all():
                    _safe_remove_file(doc.file_path)

                Offer.query.filter_by(application_id=app.id).delete()
                for intv in Interview.query.filter_by(application_id=app.id).all():
                    Interviewer.query.filter_by(interview_id=intv.id).delete()
                    db.session.delete(intv)
                ApplicationStatusHistory.query.filter_by(application_id=app.id).delete()
                ApplicationDocument.query.filter_by(application_id=app.id).delete()
                Message.query.filter_by(application_id=app.id).delete()
                Shortlist.query.filter_by(application_id=app.id).delete()
                db.session.delete(app)

            db.session.delete(candidate)

        # 2. Employer / Recruiter Cascade
        recruiter = getattr(user, 'recruiter', None)
        if recruiter:
            rid = recruiter.id
            company = recruiter.company
            if company:
                coid = company.id
                other_recs = Recruiter.query.filter(Recruiter.company_id == coid, Recruiter.id != rid).count()
                if other_recs == 0:
                    _safe_remove_file(getattr(company, 'logo_path', None))
                    _safe_remove_file(getattr(company, 'logo_url', None))
                    CompanyHiringField.query.filter_by(company_id=coid).delete()
                    CompanyEmploymentType.query.filter_by(company_id=coid).delete()

                    for job in Job.query.filter_by(company_id=coid).all():
                        for app in Application.query.filter_by(job_id=job.id).all():
                            for doc in ApplicationDocument.query.filter_by(application_id=app.id).all():
                                _safe_remove_file(doc.file_path)

                            Offer.query.filter_by(application_id=app.id).delete()
                            for intv in Interview.query.filter_by(application_id=app.id).all():
                                Interviewer.query.filter_by(interview_id=intv.id).delete()
                                db.session.delete(intv)
                            ApplicationStatusHistory.query.filter_by(application_id=app.id).delete()
                            ApplicationDocument.query.filter_by(application_id=app.id).delete()
                            Message.query.filter_by(application_id=app.id).delete()
                            Shortlist.query.filter_by(application_id=app.id).delete()
                            db.session.delete(app)

                        JobSkill.query.filter_by(job_id=job.id).delete()
                        SavedJob.query.filter_by(job_id=job.id).delete()
                        Shortlist.query.filter_by(job_id=job.id).delete()
                        Complaint.query.filter_by(against_job_id=job.id).delete()
                        db.session.delete(job)

                    db.session.delete(company)
            
            Shortlist.query.filter_by(shortlisted_by=rid).delete()
            db.session.delete(recruiter)

        # 3. Clean up all user-linked rows across remaining tables
        Interviewer.query.filter_by(user_id=user.id).delete()
        ApplicationStatusHistory.query.filter_by(changed_by=user.id).delete()
        Notification.query.filter_by(user_id=user.id).delete()
        Message.query.filter((Message.sender_id == user.id) | (Message.receiver_id == user.id)).delete()
        
        if user_email:
            EmailVerification.query.filter_by(email=user_email).delete()

        AiChatMessage.query.filter_by(user_id=user.id).delete()
        Complaint.query.filter((Complaint.user_id == user.id) | (Complaint.raised_by == user.id)).delete()
        AuditLog.query.filter_by(user_id=user.id).delete()

        # 4. Nullify any admin/reviewer references
        User.query.filter_by(reviewed_by_id=user.id).update({'reviewed_by_id': None})
        Candidate.query.filter_by(location_verified_by_id=user.id).update({'location_verified_by_id': None})
        Job.query.filter_by(approved_by=user.id).update({'approved_by': None})

        # 5. Delete the User row itself
        db.session.delete(user)
        db.session.commit()
        return True, "Account successfully and permanently removed."
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error permanently deleting user {user_id}: {e}", exc_info=True)
        return False, str(e)


def build_filtered_job_query(query, search=None, location=None, category=None, employment_type=None, salary=None):
    """
    Unified high-precision filter builder for Job queries across /explore and /jobs routes.
    Supports acronym expansions (e.g. ML -> Machine Learning), exact phrase matching,
    strict city location matching, and salary threshold filtering.
    """
    from sqlalchemy import or_, and_, select
    from app.models import Job, JobCategory, JobSkill
    from app.extensions import db
    import re

    # 1. Keyword search (search / q)
    if search and str(search).strip():
        q_term = str(search).strip()
        q_lower = q_term.lower()

        # Acronym & Synonym dictionary
        ACRONYM_MAP = {
            'ml': ['ml', 'machine learning'],
            'machine learning': ['ml', 'machine learning'],
            'ai': ['ai', 'artificial intelligence'],
            'artificial intelligence': ['ai', 'artificial intelligence'],
            'bi': ['bi', 'business intelligence'],
            'business intelligence': ['bi', 'business intelligence'],
            'ui': ['ui', 'ux', 'ui/ux', 'user interface'],
            'ux': ['ui', 'ux', 'ui/ux', 'user experience'],
            'ui/ux': ['ui', 'ux', 'ui/ux', 'user interface', 'user experience'],
            'full stack': ['full stack', 'fullstack'],
            'fullstack': ['full stack', 'fullstack'],
            'frontend': ['frontend', 'front-end', 'front end'],
            'backend': ['backend', 'back-end', 'back end'],
        }

        search_phrases = ACRONYM_MAP.get(q_lower, [q_term])

        term_filters = []
        skill_filters = []
        cat_filters = []

        for phrase in search_phrases:
            phrase_clean = phrase.strip()
            if len(phrase_clean) <= 3:
                # Word-boundary matching for short acronyms to avoid matching "HTML5", "email", etc.
                wb_patterns = [
                    phrase_clean,
                    f'{phrase_clean} %',
                    f'% {phrase_clean}',
                    f'% {phrase_clean} %',
                    f'%/{phrase_clean}%',
                    f'%{phrase_clean}/%',
                    f'%-{phrase_clean}%',
                    f'%{phrase_clean}-%',
                    f'%& {phrase_clean}%',
                    f'%{phrase_clean} &%',
                    f'% {phrase_clean}.%',
                    f'% {phrase_clean},%',
                    f'%({phrase_clean})%'
                ]
                for pat in wb_patterns:
                    term_filters.append(Job.title.ilike(pat))
                    term_filters.append(Job.description.ilike(pat))
                    skill_filters.append(JobSkill.skill_name.ilike(pat))
                    cat_filters.append(JobCategory.name.ilike(pat))
            else:
                p = f'%{phrase_clean}%'
                term_filters.append(Job.title.ilike(p))
                term_filters.append(Job.description.ilike(p))
                skill_filters.append(JobSkill.skill_name.ilike(p))
                cat_filters.append(JobCategory.name.ilike(p))

        # Skill match subquery using select()
        skills_subq = select(JobSkill.job_id).filter(or_(*skill_filters))

        # Category match subquery using select()
        cat_subq = select(Job.id).join(JobCategory).filter(or_(*cat_filters))

        query = query.filter(or_(*term_filters, Job.id.in_(skills_subq), Job.id.in_(cat_subq)))

    # 2. Location filter
    if location and str(location).strip() and str(location).strip() not in ('All Cities', 'All', 'all', ''):
        loc_str = str(location).strip()
        if loc_str.lower() == 'remote':
            query = query.filter(or_(Job.location.ilike('%remote%'), Job.employment_type.ilike('%remote%')))
        else:
            query = query.filter(Job.location.ilike(f'%{loc_str}%'))

    # 3. Category filter
    if category and str(category).strip() not in ('All Categories', 'All Positions', 'All', 'all', ''):
        cat_str = str(category).strip()
        if cat_str.isdigit():
            query = query.filter(Job.category_id == int(cat_str))
        else:
            query = query.join(JobCategory).filter(JobCategory.name.ilike(f'%{cat_str}%'))

    # 4. Employment type filter
    if employment_type and str(employment_type).strip() and str(employment_type).strip() not in ('All Types', 'All', 'all', ''):
        emp_str = str(employment_type).strip().lower()
        if 'full' in emp_str:
            query = query.filter(or_(Job.employment_type.ilike('%full%'), Job.employment_type == 'Full-time', Job.employment_type == 'Full Time'))
        elif 'part' in emp_str:
            query = query.filter(or_(Job.employment_type.ilike('%part%'), Job.employment_type == 'Part-time'))
        elif 'remote' in emp_str:
            query = query.filter(or_(Job.employment_type.ilike('%remote%'), Job.location.ilike('%remote%')))
        elif 'intern' in emp_str:
            query = query.filter(or_(Job.employment_type.ilike('%intern%'), Job.employment_type == 'Internship'))
        elif 'contract' in emp_str:
            query = query.filter(or_(Job.employment_type.ilike('%contract%'), Job.employment_type == 'Contract'))
        else:
            query = query.filter(Job.employment_type.ilike(f'%{emp_str}%'))

    # 5. Salary filter
    if salary and str(salary).strip() and str(salary).strip() not in ('Any Salary', 'All', 'all', ''):
        sal_str = str(salary).strip()
        try:
            clean_sal = int(re.sub(r'\D', '', sal_str))
            if clean_sal > 0:
                query = query.filter(or_(
                    Job.salary_max >= clean_sal,
                    and_(Job.salary_max.is_(None), Job.salary_min >= clean_sal),
                    Job.salary_range.ilike(f'%{clean_sal}%')
                ))
        except (ValueError, TypeError):
            pass

    return query



