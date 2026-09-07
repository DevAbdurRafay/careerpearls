from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, session, current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, oauth
from app.models import User, create_audit_log, setup_user_role
from app.auth.forms import (
    LoginForm, RegisterForm, VerifyCodeForm, ForgotPasswordForm, VerifyResetCodeForm, ResetPasswordForm, OAuthOnboardingForm,
)
from app.candidate.onboarding_store import clear_onboarding_session
from app.email_utils import (
    send_welcome_email,
    send_password_reset_email,
    send_password_reset_code_email,
    send_verification_email,
    generate_reset_token,
    verify_reset_token,
)
from app.auth.verification_store import (
    get_pending_registration,
    save_pending_registration,
    update_verification_code,
    clear_pending_registration,
    is_pending_expired,
    verify_submitted_code,
    create_registration_code,
    get_pending_password_reset,
    save_pending_password_reset,
    update_password_reset_code,
    mark_password_reset_verified,
    clear_pending_password_reset,
)
from app.candidate.onboarding_store import clear_onboarding_session
from app.button_utils import safe_button_handler, safe_flash_success, safe_flash_error, safe_redirect

auth_bp = Blueprint('auth', __name__, template_folder='templates')


def _redirect_by_role():
    if current_user.is_admin():
        return redirect(url_for('admin.dashboard'))
    if current_user.is_rejected():
        logout_user()
        session.clear()
        safe_flash_error('Your account has been rejected. Please contact support.')
        return safe_redirect('auth.login')
    # Skip approval check for OAuth users since they're already authenticated
    if current_user.needs_oauth_onboarding():
        return redirect(url_for('auth.oauth_onboarding'))
    if current_user.is_employer():
        recruiter = current_user.recruiter
        if recruiter and recruiter.company and not recruiter.company.onboarding_complete:
            return redirect(url_for('employer.onboarding'))
        return redirect(url_for('employer.dashboard'))
    if current_user.is_candidate() and _candidate_needs_onboarding():
        return redirect(url_for('candidate.onboarding'))
    if current_user.is_candidate():
        return redirect(url_for('candidate.profile'))
    return redirect(url_for('jobboard.job_list'))


def _candidate_needs_onboarding():
    from app.candidate.onboarding_store import candidate_needs_onboarding
    return candidate_needs_onboarding()


def _post_login(user, remember=False):
    if not user.is_active or user.approval_status == 'deactivated':
        if user.approval_status == 'deactivated':
            # Reactivate user account (profile data is already wiped on deactivation)
            user.is_active = True
            user.approval_status = 'approved'
            user.approval_note = "Account reactivated upon user login."
            
            # Wiping any residual profile data just in case
            if user.is_candidate() and user.candidate:
                db.session.delete(user.candidate)
            elif user.is_employer() and user.recruiter:
                if user.recruiter.company:
                    db.session.delete(user.recruiter.company)
                else:
                    db.session.delete(user.recruiter)
                    
            db.session.commit()
            flash('Welcome back! Your account has been reactivated. As per our deactivation policy, all your previous data was permanently removed. Please set up your profile to start fresh.', 'success')
        else:
            flash('Your account has been deactivated by Super Admin.', 'danger')
            return redirect(url_for('auth.login'))
    
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    
    clear_onboarding_session()
    # Always use remember=True to ensure session persists across refreshes
    login_user(user, remember=True)
    if user.needs_oauth_onboarding():
        return redirect(url_for('auth.oauth_onboarding'))
    next_page = request.args.get('next') or session.pop('oauth_next', None)
    if next_page:
        return redirect(next_page)
    # Redirect to appropriate dashboard based on role
    return _redirect_by_role()


def _start_registration_verification(name, email, password, role):
    from werkzeug.security import generate_password_hash

    email = email.lower()
    code = create_registration_code()
    expires_at = save_pending_registration(
        name,
        email,
        generate_password_hash(password),
        role,
        code,
    )

    sent, mail_error = send_verification_email(email, name.strip(), code)
    if current_app.debug:
        current_app.logger.info('Verification code for %s: %s', email, code)
    return sent, mail_error, code, expires_at


def _complete_registration(pending):
    user = User(
        name=pending['name'],
        email=pending['email'],
        role=pending['role'],
        approval_status='approved',
        privacy_policy_accepted_at=datetime.utcnow(),
        last_login_at=datetime.utcnow(),
    )
    user.password_hash = pending['password_hash']
    db.session.add(user)
    db.session.flush()
    setup_user_role(user, pending['role'], pending['name'])
    create_audit_log(
        user.id,
        'user_registered',
        'User',
        user.id,
        details=f"Role: {pending['role']}, status: approved",
    )
    db.session.commit()
    send_welcome_email(user)
    clear_pending_registration()
    login_user(user, remember=True)
    flash('Account created successfully! Welcome to CareerPearls.', 'success')
    return _redirect_by_role()


@auth_bp.route('/register', methods=['GET', 'POST'])
@safe_button_handler('auth.login')
def register():
    if current_user.is_authenticated:
        logout_user()
        session.clear()

    form = RegisterForm()
    role_param = request.args.get('role', 'candidate')
    if role_param not in ('candidate', 'employer'):
        role_param = 'candidate'
    
    # Store role hint in session for Google Auth
    session['oauth_role_hint'] = role_param
    # Mark that user is on the register page - allows new Google Auth registrations
    session['oauth_came_from_register'] = True

    if form.validate_on_submit():
        if not request.form.get('privacy_consent'):
            safe_flash_error('You must accept the Privacy Policy and Terms of Service to create an account.')
            return render_template('register.html', form=form, role=role_param)
        role = request.form.get('role', role_param)
        if role not in ('candidate', 'employer'):
            role = 'candidate'
        sent, mail_error, _code, expires_at = _start_registration_verification(
            form.name.data.strip(),
            form.email.data.lower(),
            form.password.data,
            role,
        )
        if sent:
            safe_flash_success('Verification code sent to your email. Check inbox and spam folder.')
        else:
            safe_flash_error(mail_error or 'Could not send verification email.')
        return safe_redirect(
            'auth.verify_registration',
            email=form.email.data.lower(),
            role=role,
            expires=expires_at.isoformat(),
        )

    return render_template('register.html', form=form, role=role_param)


@auth_bp.route('/verify-registration', methods=['GET', 'POST'])
def verify_registration():
    pending = get_pending_registration()
    if not pending:
        flash('Please register first.', 'warning')
        return redirect(url_for('auth.register'))

    email = pending['email']
    form = VerifyCodeForm()
    if form.validate_on_submit():
        if is_pending_expired(pending):
            flash('Verification code has expired. Please request a new code.', 'danger')
            return redirect(url_for('auth.verify_registration'))

        if not verify_submitted_code(pending, form.code.data):
            flash('Invalid verification code. Please try again.', 'danger')
            return render_template(
                'verify_registration.html',
                form=form,
                email=email,
                role=pending['role'],
                expiry_seconds=0,
            )

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            clear_pending_registration()
            role_title = existing_user.role.title() if existing_user.role else 'User'
            flash(f'An account with this email already exists as a {role_title}. Please log in or deactivate your existing account first.', 'warning')
            return redirect(url_for('auth.login'))

        return _complete_registration(pending)

    remaining = max(0, int((pending['expires_at'] - datetime.utcnow()).total_seconds()))
    return render_template(
        'verify_registration.html',
        form=form,
        email=email,
        role=pending['role'],
        expiry_seconds=remaining,
    )


@auth_bp.route('/verify-registration/resend', methods=['POST'])
def resend_verification():
    pending = get_pending_registration()
    if not pending:
        flash('Please register first.', 'warning')
        return redirect(url_for('auth.register'))

    code = create_registration_code()
    expires_at = update_verification_code(code)
    sent, mail_error = send_verification_email(pending['email'], pending['name'], code)
    if sent:
        flash('A new verification code has been sent. Check inbox and spam folder.', 'info')
    else:
        flash(f'Could not resend email: {mail_error or "Check MAIL settings in .env"}', 'danger')
    return redirect(url_for(
        'auth.verify_registration',
        email=pending['email'],
        role=pending['role'],
        expires=expires_at.isoformat(),
    ))


@auth_bp.route('/login', methods=['GET', 'POST'])
@safe_button_handler('auth.login')
def login():
    if current_user.is_authenticated:
        logout_user()
        session.clear()

    form = LoginForm()
    role_hint = request.form.get('role') or request.args.get('role', 'candidate')
    if role_hint not in ('candidate', 'employer'):
        role_hint = 'candidate'
    
    # Store role hint in session for Google Auth
    session['oauth_role_hint'] = role_hint
    # Ensure new Google Auth registrations are NOT allowed from the login page
    session.pop('oauth_came_from_register', None)

    if request.method == 'GET' and request.args.get('prompt') == 'apply':
        flash('Please log in or create an account to apply for jobs.', 'info')

    if form.validate_on_submit():
        email = form.email.data.lower()
        try:
            user = User.query.filter_by(email=email).first()
        except Exception:
            user = None
        
        if not user:
            safe_flash_error('This email is not registered. Please create an account.')
        elif user.is_admin():
            safe_flash_error('Invalid credentials. Account not found for this role.')
        elif not user.password_hash:
            safe_flash_error('This account uses social login. Please sign in with Google.')
        else:
            is_valid_pass = user.check_password(form.password.data)
            if is_valid_pass:
                # Check if user is trying to login with wrong role
                if role_hint == 'employer' and user.is_candidate():
                    safe_flash_error('Email is already registered as candidate. Please login as candidate.')
                elif role_hint == 'candidate' and user.is_employer():
                    safe_flash_error('Email is already registered as employer. Please login as employer.')
                else:
                    return _post_login(user, remember=True)
            else:
                safe_flash_error('Incorrect password. Please try again.')

    return render_template('login.html', form=form, role=role_hint)


@auth_bp.route('/logout')
def logout():
    was_admin = False
    try:
        if current_user.is_authenticated and current_user.is_admin():
            was_admin = True
    except Exception:
        pass
    clear_onboarding_session()
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    if was_admin:
        return redirect(url_for('admin.admin_login'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return _redirect_by_role()

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('This email is not registered.', 'warning')
            return render_template('forgot_password.html', form=form)

        code = create_registration_code()
        expires_at = save_pending_password_reset(email, code)
        sent, mail_error = send_password_reset_code_email(email, user.name, code)
        if sent:
            flash('Verification code sent to your email. Check inbox and spam folder.', 'info')
        else:
            flash(mail_error or 'Could not send verification code email.', 'danger')

        return redirect(url_for('auth.verify_reset_code', email=email, expires=expires_at.isoformat()))
    return render_template('forgot_password.html', form=form)


@auth_bp.route('/forgot-password/verify', methods=['GET', 'POST'])
def verify_reset_code():
    if current_user.is_authenticated:
        return _redirect_by_role()

    pending = get_pending_password_reset()
    if not pending:
        flash('Please enter your email to reset password.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    email = pending['email']
    form = VerifyResetCodeForm()
    if form.validate_on_submit():
        if is_pending_expired(pending):
            flash('Verification code has expired. Please request a new code.', 'danger')
            return redirect(url_for('auth.verify_reset_code'))

        if not verify_submitted_code(pending, form.code.data):
            flash('Invalid verification code. Please try again.', 'danger')
            return render_template(
                'verify_reset_code.html',
                form=form,
                email=email,
                expiry_seconds=0,
            )

        mark_password_reset_verified()
        flash('Code verified! Please set your new password.', 'success')
        return redirect(url_for('auth.reset_password'))

    remaining = max(0, int((pending['expires_at'] - datetime.utcnow()).total_seconds()))
    return render_template(
        'verify_reset_code.html',
        form=form,
        email=email,
        expiry_seconds=remaining,
    )


@auth_bp.route('/forgot-password/resend', methods=['POST'])
def resend_reset_code():
    pending = get_pending_password_reset()
    if not pending:
        flash('Please enter your email first.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=pending['email']).first()
    name = user.name if user else 'User'

    code = create_registration_code()
    expires_at = update_password_reset_code(code)
    sent, mail_error = send_password_reset_code_email(pending['email'], name, code)
    if sent:
        flash('A new verification code has been sent to your email.', 'info')
    else:
        flash(f'Could not resend email: {mail_error or "Check MAIL settings in .env"}', 'danger')

    return redirect(url_for(
        'auth.verify_reset_code',
        email=pending['email'],
        expires=expires_at.isoformat(),
    ))


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token=None):
    if current_user.is_authenticated:
        return _redirect_by_role()

    # Legacy token fallback support
    if token:
        email = verify_reset_token(token)
        if not email:
            flash('Invalid or expired reset link.', 'danger')
            return redirect(url_for('auth.forgot_password'))
        user = User.query.filter_by(email=email).first_or_404()
    else:
        pending = get_pending_password_reset()
        if not pending or not pending.get('verified'):
            flash('Please verify your 6-digit code first.', 'warning')
            return redirect(url_for('auth.forgot_password'))
        user = User.query.filter_by(email=pending['email']).first_or_404()

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        create_audit_log(user.id, 'password_reset', 'User', user.id)
        db.session.commit()
        clear_pending_password_reset()
        flash('Password updated successfully. You can now sign in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_password.html', form=form)



@auth_bp.route('/oauth/onboarding', methods=['GET', 'POST'])
@login_required
@safe_button_handler('auth.login')
def oauth_onboarding():
    # If user already has a role, redirect them directly instead of showing confirmation
    if not current_user.needs_oauth_onboarding():
        return _redirect_by_role()

    # New user needs onboarding
    role_param = request.args.get('role')
    if role_param in ('candidate', 'employer'):
        session['oauth_role_hint'] = role_param

    role_hint = session.get('oauth_role_hint', 'candidate')
    if role_hint not in ('candidate', 'employer'):
        role_hint = 'candidate'

    if request.method == 'POST':
        action = request.form.get('action', 'confirm')
        if action == 'cancel':
            session.pop('oauth_role_hint', None)
            clear_onboarding_session()
            logout_user()
            safe_flash_success('Google sign-in cancelled.')
            return safe_redirect('auth.login')

        chosen_role = request.form.get('role', role_hint)
        if chosen_role not in ('candidate', 'employer'):
            chosen_role = 'candidate'

        try:
            current_user.role = chosen_role
            current_user.approval_status = 'approved'
            db.session.commit()
            setup_user_role(current_user, chosen_role, current_user.name)
            create_audit_log(current_user.id, 'oauth_onboarding_complete', 'User', current_user.id)
            db.session.commit()
            session.pop('oauth_role_hint', None)
            safe_flash_success(f'Welcome! Account set up as {chosen_role.title()}.')
            return _redirect_by_role()
        except Exception as e:
            current_app.logger.error(f"OAuth onboarding error: {e}")
            db.session.rollback()
            safe_flash_error('Failed to complete onboarding. Please try again.')
            return safe_redirect('auth.oauth_onboarding', role=role_hint)

    form = OAuthOnboardingForm(role=role_hint)
    return render_template('oauth_onboarding.html', form=form, role_hint=role_hint)


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

@auth_bp.route('/auth/google')
def google_login():
    if not current_app.config.get('GOOGLE_CLIENT_ID'):
        flash('Google login is not configured. Add credentials to .env', 'warning')
        return redirect(url_for('auth.login'))
    
    role = request.args.get('role', 'candidate')
    if role not in ('candidate', 'employer'):
        role = 'candidate'
    session['oauth_role_hint'] = role
    
    redirect_uri = url_for('auth.google_callback', _external=True)
    # prompt='select_account' forces Google to show the account chooser with all accounts on the device
    return oauth.google.authorize_redirect(redirect_uri, prompt='select_account')


@auth_bp.route('/auth/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get('userinfo') or oauth.google.parse_id_token(token)
    except Exception:
        flash('Google sign-in failed. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    return _handle_oauth_user(
        provider='google',
        oauth_id=userinfo['sub'],
        email=userinfo['email'].lower(),
        name=userinfo.get('name', userinfo['email'].split('@')[0]),
    )


def _handle_oauth_user(provider, oauth_id, email, name):
    role_hint = session.get('oauth_role_hint', 'candidate')
    if role_hint not in ('candidate', 'employer'):
        role_hint = 'candidate'

    # 1. Look for user by oauth credentials or email
    user = User.query.filter_by(oauth_provider=provider, oauth_id=oauth_id).first()
    if not user and provider == 'google':
        user = User.query.filter_by(google_id=oauth_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    if user:
        if not user.is_active or user.approval_status == 'deactivated':
            safe_flash_error('This account has been deactivated. Please contact support or register again.')
            return safe_redirect('auth.login', role=role_hint)

        # ROLE CONFLICT ENFORCEMENT:
        # If user attempts to log in as Candidate, but email is already registered as an Employer
        if user.role == 'employer' and role_hint == 'candidate':
            safe_flash_error('This email is already registered as an Employer. Please switch to the Employer tab to log in.')
            return safe_redirect('auth.login', role='employer')

        # If user attempts to log in as Employer, but email is already registered as a Candidate
        if user.role == 'candidate' and role_hint == 'employer':
            safe_flash_error('This email is already registered as a Candidate. Please switch to the Candidate tab to log in.')
            return safe_redirect('auth.login', role='candidate')

        # Link OAuth credentials if matching
        if not user.oauth_provider or user.oauth_provider != provider:
            user.oauth_provider = provider
            user.oauth_id = oauth_id
            if provider == 'google':
                user.google_id = oauth_id
            db.session.commit()

        # Clean up transient OAuth session flags
        session.pop('oauth_came_from_register', None)
        session.pop('oauth_role_hint', None)

        # Store temporary user ID in session and redirect to OAuth login confirmation screen
        session['temp_oauth_user_id'] = user.id
        return redirect(url_for('auth.oauth_confirm'))

    else:
        # 2. New user registration via Google with chosen role
        user = User(
            email=email,
            name=name,
            oauth_provider=provider,
            oauth_id=oauth_id,
            google_id=oauth_id if provider == 'google' else None,
            role=role_hint,
            approval_status='approved'
        )
        db.session.add(user)
        db.session.commit()
        
        # Create associated profile if candidate/employer
        if role_hint == 'candidate':
            from app.models import Candidate
            if not user.candidate:
                candidate = Candidate(user_id=user.id, full_name=name)
                db.session.add(candidate)
                db.session.commit()
        elif role_hint == 'employer':
            from app.models import Recruiter
            if not user.recruiter:
                recruiter = Recruiter(user_id=user.id)
                db.session.add(recruiter)
                db.session.commit()

        # Clean up transient OAuth session flags
        session.pop('oauth_came_from_register', None)
        session.pop('oauth_role_hint', None)

        # Log the user in directly and redirect to their appropriate dashboard
        return _post_login(user, remember=True)


@auth_bp.route('/api/user/settings', methods=['POST'])
@login_required
def update_user_settings():
    from flask import request, jsonify
    from app.extensions import db
    data = request.get_json() or {}
    theme_mode = data.get('theme_mode')
    accent_color = data.get('accent_color')
    
    if theme_mode in ('light', 'dark'):
        current_user.theme_mode = theme_mode
    if accent_color in ('purple', 'orange', 'green', 'blue'):
        current_user.accent_color = accent_color
        
    db.session.commit()
    return jsonify({'status': 'success'})


@auth_bp.route('/auth/oauth-confirm', methods=['GET', 'POST'])
def oauth_confirm():
    from flask import request, session, redirect, url_for, render_template, flash
    from app.models import User
    user_id = session.get('temp_oauth_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
        
    user = User.query.get_or_404(user_id)
    role_hint = user.role
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'confirm':
            session.pop('temp_oauth_user_id', None)
            return _post_login(user, remember=True)
        else:
            session.pop('temp_oauth_user_id', None)
            session.clear()
            flash('Google sign-in cancelled.', 'info')
            return redirect(url_for('auth.login'))
            
    return render_template('oauth_role_confirm.html', role_hint=role_hint, user_name=user.name)

