import os
from flask import Flask, redirect, url_for, flash, session, jsonify
from flask_login import current_user, logout_user, LoginManager, login_required
from config import Config, check_required_env_vars
from app.extensions import db, login_manager, migrate, mail, oauth, csrf


def create_app(config_class=Config):
    # Run env-var check immediately so misconfiguration is surfaced on startup
    # rather than causing silent OAuth failures later.
    check_required_env_vars()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure MAX_CONTENT_LENGTH is set properly for file uploads
    app.config['MAX_CONTENT_LENGTH'] = 52428800  # 50MB for certificate + resume uploads

    # Print a clear startup banner so the developer always knows the correct URL.
    base_url = app.config.get('APP_BASE_URL', 'http://localhost:5000')
    print(f'\n[CareerPearls] Serving at {base_url}  (Google OAuth redirect_uri will use this host)\n')

    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(app.root_path, '..', upload_folder)
        upload_folder = os.path.abspath(upload_folder)
    app.config['UPLOAD_FOLDER'] = upload_folder
    os.makedirs(upload_folder, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    _init_oauth(app)

    from app.auth.routes import auth_bp
    from app.candidate.routes import candidate_bp
    from app.employer.routes import employer_bp
    from app.jobboard.routes import jobboard_bp
    from app.admin.routes import admin_bp
    from app.api.routes import api_bp
    from app.ai_routes import ai_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(candidate_bp, url_prefix='/candidate')
    app.register_blueprint(employer_bp, url_prefix='/employer')
    app.register_blueprint(jobboard_bp, url_prefix='/jobs')
    admin_prefix = f'/{app.config["ADMIN_PATH"].strip("/")}'
    app.register_blueprint(admin_bp, url_prefix=admin_prefix)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(ai_bp)

    @app.route('/admin')
    @app.route('/admin/<path:legacy_path>')
    @app.route('/admin-login')
    def block_legacy_admin_urls(legacy_path=None):
        from flask import abort
        abort(404)

    @app.errorhandler(404)
    def page_not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(503)
    def service_unavailable(e):
        from flask import render_template
        return render_template('errors/503.html'), 503

    from app.candidate.onboarding_store import candidate_needs_onboarding

    with app.app_context():
        try:
            db.session.execute(db.text("ALTER TABLE applications ADD COLUMN is_read_by_employer BOOLEAN DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE applications ADD COLUMN is_read_by_candidate BOOLEAN DEFAULT 1"))
            db.session.commit()
        except Exception:
            db.session.rollback()

    @app.context_processor
    def inject_nav_profile():
        """Unified profile data for navbar — same source as profile page."""
        from flask import current_app
        from app.safe import gattr
        from app.models import Application, Job
        nav_profile = {'name': '', 'image': ''}
        org_name = ''
        org_working_since = ''
        unread_employer_apps = 0
        unread_candidate_updates = 0
        if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            try:
                if current_user.is_candidate():
                    cand = gattr(current_user, 'candidate')
                    if cand:
                        unread_candidate_updates = Application.query.filter(
                            Application.candidate_id == cand.id,
                            Application.is_read_by_candidate == False
                        ).count()
                    if current_app.config.get('TESTING_MODE'):
                        from app.candidate.onboarding_store import SessionCandidateView
                        view = SessionCandidateView()
                        nav_profile['name'] = view.full_name or current_user.name
                        nav_profile['image'] = view.profile_image or ''
                    elif cand:
                        nav_profile['name'] = cand.full_name or current_user.name
                        nav_profile['image'] = cand.profile_image or ''
                elif current_user.is_employer():
                    rec = gattr(current_user, 'recruiter')
                    company = gattr(rec, 'company') if rec else None
                    if company:
                        unread_employer_apps = Application.query.join(Job).filter(
                            Job.company_id == company.id,
                            Application.is_read_by_employer == False
                        ).count()
                    org_name = gattr(company, 'name', '') or ''
                    if company and callable(getattr(company, 'working_since_label', None)):
                        org_working_since = company.working_since_label()
            except Exception:
                pass
        return {
            'nav_profile': nav_profile,
            'org_name': org_name,
            'org_working_since': org_working_since,
            'unread_employer_apps': unread_employer_apps,
            'unread_candidate_updates': unread_candidate_updates,
        }

    app.jinja_env.globals['gattr'] = __import__('app.safe', fromlist=['gattr']).gattr

    def get_job_badge_info(job):
        if not job:
            return {'icon': 'bi-briefcase-fill', 'color': '#3b82f6', 'bg': 'rgba(59, 130, 246, 0.15)', 'border': 'rgba(59, 130, 246, 0.35)', 'text': '#60a5fa'}
        from app.safe import gattr
        title = (gattr(job, 'title', '') or '').lower()
        cat = gattr(job, 'category')
        cat_name = (gattr(cat, 'name', '') or '').lower()
        
        # 1. UI / UX / Design
        if any(k in title for k in ['ui/ux', 'ui', 'ux', 'designer', 'graphic', 'figma', 'product design', 'creative', 'art']):
            return {'icon': 'bi-palette-fill', 'color': '#ec4899', 'bg': 'rgba(236, 72, 153, 0.15)', 'border': 'rgba(236, 72, 153, 0.35)', 'text': '#f472b6'}
        # 2. DevOps / Cloud / Infrastructure
        elif any(k in title for k in ['devops', 'cloud', 'aws', 'docker', 'kubernetes', 'infrastructure', 'sysadmin', 'sre', 'ci/cd']):
            return {'icon': 'bi-cloud-check-fill', 'color': '#06b6d4', 'bg': 'rgba(6, 182, 212, 0.15)', 'border': 'rgba(6, 182, 212, 0.35)', 'text': '#38bdf8'}
        # 3. Data Science / AI / Machine Learning
        elif any(k in title for k in ['machine learning', 'ai', 'ml', 'deep learning', 'nlp', 'llm', 'computer vision', 'tensorflow', 'pytorch']):
            return {'icon': 'bi-cpu-fill', 'color': '#10b981', 'bg': 'rgba(16, 185, 129, 0.15)', 'border': 'rgba(16, 185, 129, 0.35)', 'text': '#34d399'}
        # 4. Data Analyst / BI Specialist / Analytics
        elif any(k in title for k in ['data analyst', 'bi specialist', 'business intelligence', 'power bi', 'tableau', 'analytics', 'statistics', 'sql analyst', 'data']):
            return {'icon': 'bi-bar-chart-fill', 'color': '#f59e0b', 'bg': 'rgba(245, 158, 11, 0.15)', 'border': 'rgba(245, 158, 11, 0.35)', 'text': '#fbbf24'}
        # 5. Frontend / React / Vue / Angular / Web
        elif any(k in title for k in ['react', 'frontend', 'front-end', 'angular', 'vue', 'javascript', 'typescript', 'html', 'css', 'next.js']):
            return {'icon': 'bi-code-slash', 'color': '#8b5cf6', 'bg': 'rgba(139, 92, 246, 0.15)', 'border': 'rgba(139, 92, 246, 0.35)', 'text': '#c084fc'}
        # 6. Backend / Full Stack / Python / Software Engineer
        elif any(k in title or k in cat_name for k in ['full stack', 'fullstack', 'python', 'django', 'backend', 'back-end', 'node', 'java', 'golang', 'software', 'engineer', 'developer']):
            return {'icon': 'bi-layers-fill', 'color': '#0284c7', 'bg': 'rgba(2, 132, 199, 0.15)', 'border': 'rgba(2, 132, 199, 0.35)', 'text': '#38bdf8'}
        # 7. Finance / Accounting / Banking
        elif any(k in title or k in cat_name for k in ['finance', 'financial', 'account', 'banking', 'audit', 'tax']):
            return {'icon': 'bi-bank', 'color': '#eab308', 'bg': 'rgba(234, 179, 8, 0.15)', 'border': 'rgba(234, 179, 8, 0.35)', 'text': '#facc15'}
        # 8. HR / Talent / Recruitment
        elif any(k in title or k in cat_name for k in ['hr', 'human resources', 'talent', 'recruiting', 'people', 'admin', 'manager']):
            return {'icon': 'bi-people-fill', 'color': '#14b8a6', 'bg': 'rgba(20, 184, 166, 0.15)', 'border': 'rgba(20, 184, 166, 0.35)', 'text': '#2dd4bf'}
        else:
            return {'icon': 'bi-briefcase-fill', 'color': '#3b82f6', 'bg': 'rgba(59, 130, 246, 0.15)', 'border': 'rgba(59, 130, 246, 0.35)', 'text': '#60a5fa'}

    app.jinja_env.globals['get_job_badge_info'] = get_job_badge_info

    @app.template_filter('format_dt12')
    def format_dt12_filter(dt, fmt='%Y-%m-%d %I:%M:%S %p'):
        if not dt:
            return ""
        if isinstance(dt, str):
            try:
                from dateutil import parser
                dt = parser.parse(dt)
            except Exception:
                return dt
        try:
            from datetime import timedelta, timezone
            local_tz = timezone(timedelta(hours=5))
            if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                dt = dt.astimezone(local_tz)
            else:
                dt = dt + timedelta(hours=5)
        except Exception:
            pass
        return dt.strftime(fmt)

    @app.template_filter('dt12')
    def dt12_filter(dt):
        return format_dt12_filter(dt, '%Y-%m-%d %I:%M:%S %p')

    @app.template_filter('dt12_short')
    def dt12_short_filter(dt):
        return format_dt12_filter(dt, '%Y-%m-%d %I:%M %p')

    @app.template_filter('display_filename')
    def display_filename_filter(filepath):
        if not filepath:
            return ""
        name = str(filepath).split('/')[-1].split('\\')[-1]
        if '_' in name:
            parts = name.split('_', 1)
            if len(parts[0]) in (8, 32, 36) or parts[0].isalnum():
                return parts[1]
        return name

    @app.route('/')
    def index():
        from flask import render_template
        # ALWAYS show landing page first - this is the hard rule
        # Even authenticated users see the landing page with appropriate navbar state
        from app.models import Job, User, Company, Application, Offer
        from sqlalchemy import or_
        from datetime import datetime
    
        avg_offer_value = "PKR 0"
        total_offer_value = "PKR 0"

        # Get real DB aggregates for stats (exclude hired jobs from active count)
        active_jobs = Job.query.filter(
            Job.status == 'active',
            or_(Job.approval_status == 'approved', Job.approval_status.is_(None)),
            or_(Job.is_hired == False, Job.is_hired.is_(None))
        ).count()
        registered_candidates = User.query.filter_by(role='candidate').count()
        partner_companies = Company.query.count()
        
        try:
            offers = Offer.query.with_entities(Offer.salary_offered).all()
            parsed_salaries = []
            import re
            for (sal,) in offers:
                if sal:
                    try:
                        nums = re.findall(r'\d[\d,]*', str(sal))
                        vals = [float(n.replace(',', '')) for n in nums if n.replace(',', '').isdigit() and float(n.replace(',', '')) > 0]
                        if vals:
                            parsed_salaries.append(sum(vals) / len(vals))
                    except (ValueError, TypeError):
                        pass
            
            if parsed_salaries:
                avg_val = sum(parsed_salaries) / len(parsed_salaries)
                avg_offer_value = f"PKR {avg_val:,.0f}"
                total_offer_value = avg_offer_value
        except Exception:
            avg_offer_value = "PKR 0"
            total_offer_value = "PKR 0"
        
        # Query featured active jobs from database (exclude hired jobs)
        featured_jobs = Job.query.filter(
            Job.status == 'active',
            or_(Job.approval_status == 'approved', Job.approval_status.is_(None)),
            or_(Job.is_hired == False, Job.is_hired.is_(None)),
            Job.closes_at > datetime.utcnow()
        ).order_by(Job.created_at.desc()).limit(6).all()

        # Query highest paying active job for the dynamic hero floating showcase cards (exclude hired jobs)
        all_active_jobs = Job.query.filter(
            Job.status == 'active',
            or_(Job.approval_status == 'approved', Job.approval_status.is_(None)),
            or_(Job.is_hired == False, Job.is_hired.is_(None)),
            Job.closes_at > datetime.utcnow()
        ).all()

        import re
        def get_job_max_salary(j):
            if j.salary_max is not None and j.salary_max > 0:
                return float(j.salary_max)
            if j.salary_min is not None and j.salary_min > 0:
                return float(j.salary_min)
            if j.salary_range:
                nums = re.findall(r'\d[\d,]*', j.salary_range)
                parsed = []
                for n in nums:
                    try:
                        clean_val = float(n.replace(',', ''))
                        if clean_val > 0:
                            parsed.append(clean_val)
                    except ValueError:
                        pass
                if parsed:
                    return max(parsed)
            return 0.0

        top_paying_job = max(all_active_jobs, key=get_job_max_salary, default=None) if all_active_jobs else None
        
        return render_template('landing.html', 
                            active_jobs=active_jobs,
                            registered_candidates=registered_candidates,
                            partner_companies=partner_companies,
                            avg_offer_value=avg_offer_value,
                            total_offer_value=total_offer_value,
                            featured_jobs=featured_jobs,
                            top_paying_job=top_paying_job)

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/contact', methods=['POST'])
    def contact():
        from flask import request, flash, redirect, url_for
        from app.models import ContactMessage
        from app.extensions import db
        
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        message = request.form.get('message', '').strip()
        
        # Validate phone number (exactly 11 digits)
        import re
        if not phone or len(re.sub(r'\D', '', phone)) != 11:
            flash('Please enter a valid 11-digit phone number.', 'danger')
            return redirect(url_for('index') + '#contact')
        
        # Save contact message
        contact_msg = ContactMessage(
            name=name,
            email=email,
            phone=phone,
            message=message
        )
        db.session.add(contact_msg)
        db.session.commit()
        
        # Send email notification
        try:
            from app.email_utils import send_contact_email
            send_contact_email(name, email, phone, message)
        except Exception as e:
            pass
        
        flash('Message sent Successfully We will reply soon', 'success')
        
        return redirect(url_for('index') + '#contact')

    @app.route('/explore')
    def explore():
        from flask import render_template, request, redirect, url_for
        from flask_login import current_user
        from datetime import datetime
        import re
        
        from app.models import Job, JobCategory, JobSkill
        from sqlalchemy import or_, and_
        q = request.args.get('q', '').strip()
        location = request.args.get('location', '').strip()
        salary = request.args.get('salary', '').strip()
        category_name = request.args.get('category', '').strip()
        employment_type = request.args.get('type', request.args.get('employment_type', '')).strip()
        
        query = Job.query.filter(
            Job.status == 'active',
            or_(Job.approval_status == 'approved', Job.approval_status.is_(None)),
            or_(Job.is_hired == False, Job.is_hired.is_(None)),
            or_(Job.closes_at.is_(None), Job.closes_at > datetime.utcnow())
        )
        from app.utils import build_filtered_job_query
        query = build_filtered_job_query(
            query=query,
            search=q,
            location=location,
            category=category_name,
            employment_type=employment_type,
            salary=salary
        )
                
        jobs = query.order_by(Job.created_at.desc()).all()
        categories = JobCategory.query.order_by(JobCategory.name).all()
        return render_template(
            'explore.html',
            jobs=jobs,
            categories=categories,
            q=q,
            location=location,
            salary=salary,
            category_name=category_name,
            employment_type=employment_type
        )

    @app.route('/about')
    @app.route('/about-us')
    def about():
        from flask import render_template
        return render_template('about.html')

    @app.route('/privacy-policy')
    def privacy_policy():
        from flask import render_template
        return render_template('privacy_policy.html')

    @app.route('/terms-of-service')
    def terms_of_service():
        from flask import render_template
        return render_template('terms_of_service.html')

    @app.route('/api/notifications')
    @login_required
    def get_notifications():
        from app.models import Notification
        from datetime import datetime, timedelta
        
        notifications = Notification.query.filter_by(user_id=current_user.id)\
            .order_by(Notification.created_at.desc())\
            .limit(10).all()
        
        result = []
        for n in notifications:
            time_ago = "Just now"
            if n.created_at:
                delta = datetime.utcnow() - n.created_at
                if delta < timedelta(minutes=1):
                    time_ago = "Just now"
                elif delta < timedelta(hours=1):
                    time_ago = f"{delta.seconds // 60}m ago"
                elif delta < timedelta(days=1):
                    time_ago = f"{delta.seconds // 3600}h ago"
                else:
                    time_ago = f"{delta.days}d ago"
            
            result.append({
                'id': n.id,
                'message': n.message,
                'type': n.type,
                'is_read': n.is_read,
                'time_ago': time_ago,
                'link': None  # Could be enhanced with specific links based on notification type
            })
        
        return jsonify(result)

    @app.route('/api/notifications/mark-read', methods=['POST'])
    @login_required
    def mark_notifications_read():
        from app.models import Notification, Message
        
        Notification.query.filter_by(user_id=current_user.id, is_read=False)\
            .update({'is_read': True})
        # Also mark all incoming messages as read so the floating bubble resets
        Message.query.filter_by(receiver_id=current_user.id, is_read=False)\
            .update({'is_read': True})
        db.session.commit()
        
        return jsonify({'success': True})

    @app.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
    @login_required
    def mark_single_notification_read(notification_id):
        from app.models import Notification
        
        notification = Notification.query.get_or_404(notification_id)
        if notification.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        notification.is_read = True
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/complaint', methods=['GET', 'POST'])
    @app.route('/complaint/new', methods=['GET', 'POST'])
    def register_complaint():
        from flask import render_template, request, flash, redirect, url_for
        from flask_login import current_user
        from app.models import Complaint, Job, User, Notification, create_audit_log
        from werkzeug.utils import secure_filename
        import random
        
        if not current_user.is_authenticated:
            flash('Please sign in or create an account to submit a job report.', 'warning')
            return redirect(url_for('auth.login', role='candidate', next=request.url))
        
        target_type = request.args.get('target_type') or request.form.get('target_type') or 'Job'
        target_id = request.args.get('target_id') or request.form.get('target_id') or None
        if target_id:
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                target_id = None
        
        job = None
        if target_type == 'Job' and target_id:
            job = Job.query.get(target_id)
            
        user_email = current_user.email if (current_user and current_user.is_authenticated) else None
        existing_active = None
        if user_email:
            existing_active = Complaint.query.filter(
                Complaint.complainant_email.ilike(user_email.strip()),
                Complaint.status.in_(['Pending', 'Under Review', 'In Progress'])
            ).order_by(Complaint.created_at.desc()).first()

        if request.method == 'POST':
            name = request.form.get('complainant_name', '').strip()
            email = request.form.get('complainant_email', '').strip()
            user_type = request.form.get('user_type', '').strip()
            category = request.form.get('category', '').strip()
            subject = request.form.get('subject', '').strip()
            description = request.form.get('description', '').strip()
            form_target_type = request.form.get('target_type', target_type or '').strip()
            form_target_id = request.form.get('target_id')
            
            if current_user.is_authenticated:
                name = current_user.name
                email = current_user.email
                user_type = current_user.role.title()
                user_id = current_user.id
            else:
                user_id = None
                if not name or not email:
                    flash('Please provide your name and email address.', 'danger')
                    return render_template('complaint_form.html', job=job, target_type=target_type, target_id=target_id, existing_active=existing_active)

            # Prevent duplicate / spam complaints: Single active complaint allowed per email until resolved
            pending_complaint = Complaint.query.filter(
                Complaint.complainant_email.ilike(email),
                Complaint.status.in_(['Pending', 'Under Review', 'In Progress', 'In Review', 'Open'])
            ).order_by(Complaint.created_at.desc()).first()

            if pending_complaint:
                flash(
                    f'You already have an active complaint under review ({pending_complaint.ticket_id}: "{pending_complaint.subject}"). To maintain platform integrity, a single email address can only have one open ticket at a time until it is resolved by our Trust & Safety Team.',
                    'warning'
                )
                return render_template('complaint_form.html', job=job, target_type=target_type, target_id=target_id, existing_active=pending_complaint)
            
            if not category or not description:
                flash('Please select a complaint category and provide a full description.', 'danger')
                return render_template('complaint_form.html', job=job, target_type=target_type, target_id=target_id, existing_active=existing_active)
                
            # Handle attachment upload
            attachment_url = None
            if 'attachment' in request.files:
                file = request.files['attachment']
                if file and file.filename:
                    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                    if ext in ['jpg', 'jpeg', 'png', 'pdf']:
                        filename = f"complaint_{int(datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
                        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        attachment_url = filename
                    else:
                        flash('Allowed attachment formats: JPG, PNG, PDF.', 'warning')
            
            # Generate unique human-readable Ticket ID: #CMP-XXXX
            rand_num = random.randint(1000, 9999)
            ticket_id = f"#CMP-{rand_num}"
            while Complaint.query.filter_by(ticket_id=ticket_id).first():
                ticket_id = f"#CMP-{random.randint(1000, 9999)}"
                
            # Intelligently assign Reported Entity Target
            if job:
                final_target_type = 'Job'
                final_target_id = job.id
                against_job_id = job.id
            elif form_target_type and form_target_type not in ('Job', 'General', ''):
                final_target_type = form_target_type
                final_target_id = int(form_target_id) if form_target_id and form_target_id.isdigit() else None
                against_job_id = None
            else:
                if category in ('UI Bug', 'UI Bug / Visual Glitch', 'Technical Bug', 'Payment Issue', 'Login/Account Access Issue', 'Platform Bug'):
                    final_target_type = 'Platform / UI'
                    final_target_id = None
                    against_job_id = None
                elif category in ('Employer Not Responding', 'Harassment/Inappropriate Behavior', 'Scam/Fraud Request'):
                    final_target_type = 'Employer'
                    final_target_id = None
                    against_job_id = None
                elif category in ('Fake Candidate Profile', 'Spam Applications', 'No-Show Candidate'):
                    final_target_type = 'Candidate'
                    final_target_id = None
                    against_job_id = None
                elif category in ('Fake Job Listing',):
                    final_target_type = 'Job'
                    final_target_id = int(form_target_id) if form_target_id and form_target_id.isdigit() else None
                    against_job_id = final_target_id
                else:
                    final_target_type = form_target_type or 'General Support'
                    final_target_id = int(form_target_id) if form_target_id and form_target_id.isdigit() else None
                    against_job_id = None

            complaint = Complaint(
                ticket_id=ticket_id,
                user_id=user_id,
                raised_by=user_id,
                complainant_name=name,
                complainant_email=email,
                complainant_role=user_type or ('Candidate' if current_user.is_authenticated and current_user.is_candidate() else ('Employer' if current_user.is_authenticated and current_user.is_employer() else 'Guest')),
                reported_entity_type=final_target_type,
                reported_entity_id=final_target_id,
                against_job_id=against_job_id,
                category=category,
                subject=subject or f"Complaint: {category}",
                description=description,
                attachment_url=attachment_url,
                status='Pending',
            )
            db.session.add(complaint)
            
            if user_id:
                create_audit_log(user_id, 'complaint_submitted', 'Complaint', None, f"Ticket {ticket_id}")
                db.session.add(Notification(
                    user_id=user_id,
                    message=f"Your complaint {ticket_id} has been registered and is pending admin review.",
                    type='system'
                ))
            db.session.commit()
            
            # Send confirmation email
            try:
                from app.email_utils import send_complaint_confirmation_email
                send_complaint_confirmation_email(email, name, ticket_id, category, subject or f"Complaint: {category}", description)
            except Exception as e:
                app.logger.error(f"Failed to send complaint confirmation email: {e}")
                
            flash(f'Your complaint has been successfully submitted with Ticket ID: {ticket_id}. We have also sent a confirmation to your email.', 'success')
            return redirect(url_for('index'))
            
        return render_template('complaint_form.html', job=job, target_type=target_type, target_id=target_id, existing_active=existing_active)

    try:
        with app.app_context():
            db.create_all()
            _ensure_schema_columns()
            _seed_defaults()
    except Exception as e:
        app.logger.warning(f"Database schema/seed startup check notice: {e}")

    
    @app.before_request
    def check_user_active_status():
        from flask_login import current_user, logout_user
        from flask import session, flash, redirect, url_for, request
        if current_user.is_authenticated and not current_user.is_admin():
            if not getattr(current_user, 'is_active', True):
                reason = getattr(current_user, 'approval_note', None) or 'Account access restricted by administrator.'
                logout_user()
                session.clear()
                flash(f'Your account has been deactivated by Super Admin. Reason: {reason}', 'danger')
                return redirect(url_for('auth.login'))

    # Register CLI command for interview reminders
    @app.cli.command("send-interview-reminders")
    def send_interview_reminders_command():
        """Process and send 24-hour upcoming interview reminder emails."""
        from app.reminder_service import process_interview_reminders
        count = process_interview_reminders(app)
        print(f"[CareerPearls] Processed interview reminders. {count} reminder email(s) dispatched.")

    with app.app_context():
        try:
            _ensure_schema_columns()
        except Exception as e:
            app.logger.warning(f"Schema self-healing check note: {e}")

    # Start background interview reminder scheduler (runs every 15 mins)
    if not app.config.get('TESTING'):
        try:
            from app.reminder_service import start_reminder_scheduler
            start_reminder_scheduler(app)
        except Exception as e:
            app.logger.warning(f"Could not start reminder scheduler: {e}")

    return app


def _ensure_schema_columns():
    """Add new columns to existing SQLite databases without a full migration."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'candidates' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('candidates')}
        additions = {
            'work_mode': 'VARCHAR(30)',
            'has_internship': 'BOOLEAN',
            'internship_details': 'VARCHAR(500)',
            'github_url': 'VARCHAR(255)',
            'linkedin_url': 'VARCHAR(255)',
            'kaggle_url': 'VARCHAR(255)',
            'portfolio_url': 'VARCHAR(255)',
            'is_location_verified': 'BOOLEAN DEFAULT FALSE',
            'location_verified_at': 'DATETIME',
            'location_verified_by_id': 'INTEGER',
            'onboarding_complete': 'BOOLEAN DEFAULT FALSE',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE candidates ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'companies' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('companies')}
        additions = {
            'domain': 'VARCHAR(200)',
            'official_email': 'VARCHAR(120)',
            'ntn_id': 'VARCHAR(100)',
            'phone': 'VARCHAR(50)',
            'location': 'VARCHAR(120)',
            'industry': 'VARCHAR(100)',
            'website': 'VARCHAR(200)',
            'description': 'TEXT',
            'is_verified': 'BOOLEAN DEFAULT FALSE',
            'verification_status': "VARCHAR(30) DEFAULT 'Pending Verification'",
            'rejection_reason': 'TEXT',
            'organization_type': 'VARCHAR(50)',
            'company_size': 'VARCHAR(30)',
            'employment_types': 'VARCHAR(255)',
            'working_since_months': 'INTEGER',
            'logo_path': 'VARCHAR(255)',
            'founded_date': 'DATE',
            'onboarding_complete': 'BOOLEAN DEFAULT FALSE',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE companies ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'jobs' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('jobs')}
        additions = {
            'requirements': 'TEXT',
            'description': 'TEXT',
            'location': 'VARCHAR(120)',
            'salary_range': 'VARCHAR(80)',
            'salary_min': 'INTEGER',
            'salary_max': 'INTEGER',
            'employment_type': 'VARCHAR(50)',
            'experience_required': 'VARCHAR(80)',
            'status': "VARCHAR(20) DEFAULT 'active'",
            'approval_status': "VARCHAR(20) DEFAULT 'pending'",
            'approved_by': 'INTEGER',
            'posted_by': 'INTEGER',
            'logo_path': 'VARCHAR(255)',
            'is_hired': 'BOOLEAN DEFAULT FALSE',
            'created_at': 'TIMESTAMP DEFAULT now()',
            'updated_at': 'TIMESTAMP DEFAULT now()',
            'closes_at': 'TIMESTAMP',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE jobs ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'applications' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('applications')}
        app_additions = {
            'rejection_reason': 'TEXT',
            'withdrawn_at': 'TIMESTAMP',
        }
        for name, col_type in app_additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE applications ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'users' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('users')}
        additions = {
            'theme_mode': "VARCHAR(10) DEFAULT 'light'",
            'accent_color': "VARCHAR(15) DEFAULT 'purple'",
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE users ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'candidate_education' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('candidate_education')}
        additions = {
            'field_of_study': 'VARCHAR(120)',
            'is_current': 'BOOLEAN DEFAULT FALSE',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE candidate_education ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'users' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('users')}
        additions = {
            'role': "VARCHAR(20) DEFAULT 'candidate'",
            'role_id': 'VARCHAR(20)',
            'name': 'VARCHAR(120)',
            'password_hash': 'VARCHAR(256)',
            'is_active': 'BOOLEAN DEFAULT TRUE',
            'oauth_provider': 'VARCHAR(50)',
            'oauth_id': 'VARCHAR(255)',
            'google_id': 'VARCHAR(120)',
            'approval_status': "VARCHAR(20) DEFAULT 'approved'",
            'approval_note': 'TEXT',
            'reviewed_at': 'TIMESTAMP',
            'reviewed_by_id': 'INTEGER',
            'created_at': 'TIMESTAMP DEFAULT now()',
            'updated_at': 'TIMESTAMP DEFAULT now()',
            'last_login_at': 'TIMESTAMP',
            'privacy_policy_accepted_at': 'TIMESTAMP',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE users ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'recruiters' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('recruiters')}
        additions = {
            'name': 'VARCHAR(120)',
            'title': 'VARCHAR(120)',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE recruiters ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'contact_messages' not in inspector.get_table_names():
        try:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS contact_messages (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(120) NOT NULL,
                    phone VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    sent_at TIMESTAMP NOT NULL
                )
            '''))
            db.session.commit()
        except Exception:
            db.session.rollback()
    
    # Add missing columns to applications table
    if 'applications' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('applications')}
        additions = {
            'screening_notes': 'TEXT',
            'rejection_reason': 'TEXT',
            'on_hold': 'BOOLEAN DEFAULT FALSE',
            'hold_reason': 'TEXT',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE applications ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'audit_logs' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('audit_logs')}
        if 'details' not in existing:
            try:
                db.session.execute(text('ALTER TABLE audit_logs ADD COLUMN details TEXT'))
                db.session.commit()
            except Exception:
                db.session.rollback()
    if 'complaints' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('complaints')}
        additions = {
            'complainant_name': 'VARCHAR(120)',
            'complainant_email': 'VARCHAR(120)',
            'complainant_phone': 'VARCHAR(50)',
            'complainant_role': 'VARCHAR(50)',
            'subject': 'VARCHAR(200)',
            'category': 'VARCHAR(100)',
            'attachment_url': 'VARCHAR(500)',
            'admin_note': 'TEXT',
            'ticket_id': 'VARCHAR(50)',
        }
        for name, col_type in additions.items():
            if name not in existing:
                try:
                    db.session.execute(text(f'ALTER TABLE complaints ADD COLUMN {name} {col_type}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    if 'interviews' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('interviews')}
        if 'reminder_sent' not in existing:
            try:
                db.session.execute(text('ALTER TABLE interviews ADD COLUMN reminder_sent BOOLEAN DEFAULT FALSE'))
                db.session.commit()
            except Exception:
                db.session.rollback()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _init_oauth(app):
    oauth.init_app(app)

    if app.config.get('GOOGLE_CLIENT_ID'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )


def _seed_defaults():
    from flask import current_app
    from app.models import User, JobCategory, Company, Recruiter, Job, JobSkill
    from app.utils import get_or_create_user
    from datetime import datetime, timedelta

    if not JobCategory.query.first():
        for name in ['Engineering', 'Design', 'Marketing', 'Sales',
                     'Finance', 'Operations', 'Human Resources', 'Other']:
            db.session.add(JobCategory(name=name))
        db.session.commit()

    # Auto-approve any pending users
    User.query.filter_by(approval_status='pending').update({'approval_status': 'approved'})
    db.session.commit()

    admin_email = current_app.config.get('ADMIN_EMAIL')
    admin_password = current_app.config.get('ADMIN_PASSWORD')
    if not admin_email or not admin_password:
        print('[CareerPearls] Set ADMIN_EMAIL and ADMIN_PASSWORD in .env, then run: python scripts/set_admin.py')
    else:
        from werkzeug.security import generate_password_hash
        admin_user, _created = get_or_create_user(
            admin_email,
            defaults={
                'name': 'Administrator',
                'role': 'admin',
                'approval_status': 'approved',
                'password_hash': generate_password_hash(admin_password)
            },
            update={'role': 'admin', 'approval_status': 'approved'},
        )
        if admin_password:
            admin_user.set_password(admin_password)
        admin_user.is_active = True
        admin_user.approval_status = 'approved'
        db.session.commit()

    # Seed Analysis Workforce recruiter account and featured jobs
    recruiter_email = 'analysis.workforce@gmail.com'
    rec_user = User.query.filter_by(email=recruiter_email).first()
    if not rec_user:
        rec_user = User(
            name='Analysis Workforce Recruiter',
            email=recruiter_email,
            role='employer',
            approval_status='approved',
            is_active=True,
            privacy_policy_accepted_at=datetime.utcnow()
        )
        rec_user.set_password('Admin123456!')
        db.session.add(rec_user)
        db.session.commit()
    else:
        rec_user.role = 'employer'
        rec_user.approval_status = 'approved'
        rec_user.is_active = True
        db.session.commit()

    # Seed Company for Analysis Workforce
    company = Company.query.filter_by(official_email=recruiter_email).first()
    if not company:
        company = Company(
            name='Analysis Workforce',
            official_email=recruiter_email,
            domain='analysisworkforce.com',
            website='https://analysisworkforce.com',
            industry='Technology & Analytics',
            location='Karachi, Pakistan',
            phone='03093548831',
            company_size='51-200',
            is_verified=True,
            verification_status='Approved',
            description='Leading workforce intelligence and technology solutions provider empowering great talent.',
            onboarding_complete=True
        )
        db.session.add(company)
        db.session.commit()
    else:
        company.is_verified = True
        company.verification_status = 'Approved'
        db.session.commit()

    # Link Recruiter profile
    recruiter = Recruiter.query.filter_by(user_id=rec_user.id).first()
    if not recruiter:
        recruiter = Recruiter(
            user_id=rec_user.id,
            company_id=company.id,
            name='Analysis Workforce',
            title='Talent Acquisition Lead'
        )
        db.session.add(recruiter)
        db.session.commit()
    elif recruiter.company_id != company.id:
        recruiter.company_id = company.id
        db.session.commit()

    # Ensure categories exist
    eng_cat = JobCategory.query.filter_by(name='Engineering').first() or JobCategory.query.first()
    des_cat = JobCategory.query.filter_by(name='Design').first() or eng_cat
    fin_cat = JobCategory.query.filter_by(name='Finance').first() or eng_cat

    # Sample jobs seeding (Disabled so database stays clean when cleared)
    if False and company.jobs.count() == 0:
        featured_defs = [
            {
                'title': 'Senior Full Stack Python Developer',
                'category_id': eng_cat.id,
                'location': 'Karachi',
                'salary_range': 'PKR 140,000 - 220,000',
                'salary_min': 140000,
                'salary_max': 220000,
                'employment_type': 'full_time',
                'experience_required': '3-5 yrs',
                'description': '<p>We are seeking a high-caliber Senior Full Stack Python Developer to engineer scalable microservices, optimize PostgreSQL data models, and develop high-concurrency API integrations.</p><h6>Key Responsibilities:</h6><ul><li>Architect and maintain robust Flask/Django backend APIs.</li><li>Design secure RESTful endpoints and PostgreSQL relational schemas.</li><li>Build reactive frontend components using React and Tailwind CSS.</li><li>Lead code reviews, automated unit testing, and Docker container deployments.</li></ul>',
                'requirements': "Bachelor's in CS/SE; 3+ years experience with Python (Flask/Django), PostgreSQL, Redis, React, and Git.",
                'skills': ['Python', 'PostgreSQL', 'React.js', 'REST API', 'Docker']
            },
            {
                'title': 'AI & Machine Learning Engineer',
                'category_id': eng_cat.id,
                'location': 'Remote',
                'salary_range': 'PKR 180,000 - 280,000',
                'salary_min': 180000,
                'salary_max': 280000,
                'employment_type': 'remote',
                'experience_required': '2-4 yrs',
                'description': '<p>Join our AI Research & Development team to build production-grade deep learning models, natural language processing pipelines, and predictive analytics engines.</p><h6>Key Responsibilities:</h6><ul><li>Train and fine-tune large language models (LLMs) and computer vision architectures.</li><li>Deploy low-latency inference microservices using FastAPI and Docker.</li><li>Collaborate with data engineers to optimize feature engineering and vector databases.</li></ul>',
                'requirements': 'Proficiency in Python, PyTorch/TensorFlow, Scikit-Learn, Pandas, HuggingFace, and Vector DBs.',
                'skills': ['Python', 'Machine Learning', 'TensorFlow', 'PyTorch', 'Data Analysis']
            },
            {
                'title': 'Senior UI/UX Product Designer',
                'category_id': des_cat.id,
                'location': 'Lahore',
                'salary_range': 'PKR 100,000 - 160,000',
                'salary_min': 100000,
                'salary_max': 160000,
                'employment_type': 'full_time',
                'experience_required': '3+ yrs',
                'description': '<p>We are looking for a creative UI/UX Product Designer to conceptualize intuitive user journeys, craft comprehensive design systems, and translate complex technical requirements into elegant visual interfaces.</p><h6>Key Responsibilities:</h6><ul><li>Build interactive high-fidelity prototypes and design systems in Figma.</li><li>Conduct user interviews, usability testing, and wireframing.</li><li>Work closely with frontend engineers to ensure pixel-perfect implementation.</li></ul>',
                'requirements': 'Strong portfolio of shipped SaaS/web products; mastery of Figma, Design Tokens, wireframing, and usability heuristics.',
                'skills': ['Figma', 'UI/UX Research', 'Wireframing', 'Prototyping', 'Design Systems']
            },
            {
                'title': 'Cloud DevOps & Kubernetes Engineer',
                'category_id': eng_cat.id,
                'location': 'Islamabad',
                'salary_range': 'PKR 160,000 - 240,000',
                'salary_min': 160000,
                'salary_max': 240000,
                'employment_type': 'full_time',
                'experience_required': '3-5 yrs',
                'description': '<p>Lead our cloud infrastructure automation, CI/CD pipelines, and high-availability Kubernetes deployments across AWS and multi-cloud environments.</p><h6>Key Responsibilities:</h6><ul><li>Automate infrastructure using Terraform and Ansible.</li><li>Manage multi-cluster Kubernetes deployments, ingress controllers, and Helm charts.</li><li>Maintain Prometheus and Grafana observability and real-time monitoring.</li></ul>',
                'requirements': 'Expertise with AWS, Docker, Kubernetes, Terraform, Linux, and GitHub Actions CI/CD.',
                'skills': ['Docker', 'Kubernetes', 'AWS', 'CI/CD', 'Linux']
            },
            {
                'title': 'Data Analyst & BI Specialist',
                'category_id': fin_cat.id,
                'location': 'Karachi',
                'salary_range': 'PKR 90,000 - 140,000',
                'salary_min': 90000,
                'salary_max': 140000,
                'employment_type': 'full_time',
                'experience_required': '2-4 yrs',
                'description': '<p>Drive data-informed business intelligence by creating interactive Power BI dashboards, automated SQL ETL workflows, and executive performance reports.</p><h6>Key Responsibilities:</h6><ul><li>Write complex SQL analytical queries, window functions, and views.</li><li>Build Power BI and Tableau dashboards with DAX calculations.</li><li>Perform exploratory data analysis and provide actionable growth insights.</li></ul>',
                'requirements': '2+ years analytical experience; advanced SQL, Power BI, Excel modeling, and statistical analysis.',
                'skills': ['SQL', 'Power BI', 'Excel', 'Statistics', 'Data Analysis']
            },
            {
                'title': 'Frontend React / Next.js Engineer',
                'category_id': eng_cat.id,
                'location': 'Lahore',
                'salary_range': 'PKR 110,000 - 170,000',
                'salary_min': 110000,
                'salary_max': 170000,
                'employment_type': 'full_time',
                'experience_required': '2-4 yrs',
                'description': '<p>Build modern, ultra-responsive web applications with React.js, Next.js, TypeScript, and modern CSS libraries. Collaborate with backend architects to deliver smooth, high-speed UX.</p><h6>Key Responsibilities:</h6><ul><li>Develop component-driven web applications using React and Next.js.</li><li>Integrate RESTful APIs and handle optimistic UI updates and state management.</li><li>Optimize frontend Core Web Vitals, accessibility, and responsive layouts.</li></ul>',
                'requirements': 'Proficiency in React.js, Next.js, TypeScript, HTML5, CSS3, Tailwind CSS, and RESTful APIs.',
                'skills': ['React.js', 'Next.js', 'TypeScript', 'Tailwind CSS', 'HTML5']
            },
        ]
        for f_def in featured_defs:
            job = Job(
                company_id=company.id,
                posted_by=recruiter.id,
                title=f_def['title'],
                category_id=f_def['category_id'],
                location=f_def['location'],
                salary_range=f_def['salary_range'],
                salary_min=f_def['salary_min'],
                salary_max=f_def['salary_max'],
                employment_type=f_def['employment_type'],
                experience_required=f_def['experience_required'],
                description=f_def['description'],
                requirements=f_def['requirements'],
                status='active',
                approval_status='approved',
                created_at=datetime.utcnow(),
                closes_at=datetime.utcnow() + timedelta(days=90)
            )
            db.session.add(job)
            db.session.flush()
            for s_name in f_def['skills']:
                db.session.add(JobSkill(job_id=job.id, skill_name=s_name, is_required=True))
        db.session.commit()

