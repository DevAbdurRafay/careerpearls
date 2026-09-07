import random
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from flask import render_template, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash

VERIFICATION_EXPIRY_SECONDS = 120  # 2 minutes

def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_reset_token(email):
    return _serializer().dumps(email, salt='password-reset')


def verify_reset_token(token, max_age=3600):
    try:
        return _serializer().loads(token, salt='password-reset', max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def generate_verification_code():
    return f'{random.randint(0, 999999):06d}'


def hash_verification_code(code):
    return generate_password_hash(code)


def check_verification_code(code_hash, code):
    return check_password_hash(code_hash, code.strip())


def _friendly_mail_error(error_text):
    if not error_text:
        return 'Could not send email. Check MAIL settings in .env and restart the server.'
    err = str(error_text).lower()
    if '535' in err or 'badcredentials' in err or 'username and password not accepted' in err:
        return (
            'Gmail rejected the App Password. Fix: (1) Delete old App Password at '
            'myaccount.google.com/apppasswords and create a NEW one for Mail. '
            '(2) MAIL_USERNAME must exactly match that Gmail account. '
            '(3) Save .env without quotes, restart server. '
            '(4) If still failing, open accounts.google.com/DisplayUnlockCaptcha while logged in, '
            'then run: python scripts/check_mail.py'
        )
    return f'Could not send email: {error_text}'


def verification_expires_at():
    minutes = current_app.config.get('VERIFICATION_CODE_EXPIRY_MINUTES', 2)
    return datetime.utcnow() + timedelta(minutes=minutes)


def _sender_address():
    username = current_app.config.get('MAIL_USERNAME')
    return formataddr(('CareerPearls', username))


def _smtp_attempts():
    cfg = current_app.config
    server = cfg.get('MAIL_SERVER', 'smtp.gmail.com')
    attempts = []

    if cfg.get('MAIL_USE_SSL'):
        attempts.append(('ssl', int(cfg.get('MAIL_PORT', 465))))
    else:
        attempts.append(('starttls', int(cfg.get('MAIL_PORT', 587))))
        if int(cfg.get('MAIL_PORT', 587)) != 465:
            attempts.append(('ssl', 465))

    return server, attempts


def _smtp_send(message, recipients):
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    server_host, attempts = _smtp_attempts()
    last_error = None
    context = ssl.create_default_context()

    for mode, port in attempts:
        try:
            if mode == 'ssl':
                with smtplib.SMTP_SSL(server_host, port, context=context, timeout=30) as smtp:
                    smtp.login(username, password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(server_host, port, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    smtp.login(username, password)
                    smtp.send_message(message)
            current_app.logger.info('Email sent via %s:%s (%s) to %s', server_host, port, mode, recipients)
            return True, None
        except Exception as exc:
            last_error = exc
            current_app.logger.warning('SMTP %s:%s (%s) failed: %s', server_host, port, mode, exc)

    err = str(last_error) if last_error else 'Unknown SMTP error'
    current_app.logger.error('All SMTP attempts failed for %s: %s', recipients, err)
    return False, _friendly_mail_error(err)


def send_email(subject, recipients, template=None, plain_body=None, **kwargs):
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    if not username or not password:
        msg = 'Email is not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env'
        current_app.logger.warning('Mail not configured — skipping email to %s', recipients)
        return False, msg

    if len(password) != 16:
        current_app.logger.warning('MAIL_PASSWORD length is %s (expected 16 for Gmail App Password)', len(password))

    kwargs.setdefault('app_base_url', current_app.config.get('APP_BASE_URL', 'http://127.0.0.1:5000'))
    kwargs.setdefault('year', datetime.utcnow().year)

    if template and template.endswith('.html'):
        try:
            html_body = render_template(f'email/{template}', **kwargs)
        except Exception:
            html_body = f"<div style='font-family:sans-serif;line-height:1.6;color:#333;padding:20px;'><h3 style='color:#0284c7;'>{subject}</h3><p style='white-space:pre-wrap;'>{plain_body or ''}</p><hr style='border:none;border-top:1px solid #eee;margin-top:20px;'><p style='color:#888;font-size:12px;'>CareerPearls — Where Great Talent Meets Great Opportunity</p></div>"
    else:
        html_body = f"<div style='font-family:sans-serif;line-height:1.6;color:#333;padding:20px;'><h3 style='color:#0284c7;'>{subject}</h3><p style='white-space:pre-wrap;'>{plain_body or ''}</p><hr style='border:none;border-top:1px solid #eee;margin-top:20px;'><p style='color:#888;font-size:12px;'>CareerPearls — Where Great Talent Meets Great Opportunity</p></div>"

    if plain_body is None:
        plain_body = _plain_text_from_html(html_body)

    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = _sender_address()
    message['To'] = ', '.join(recipients)
    message.attach(MIMEText(plain_body, 'plain', 'utf-8'))
    message.attach(MIMEText(html_body, 'html', 'utf-8'))

    return _smtp_send(message, recipients)


def _plain_text_from_html(html):
    import re
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.I | re.S)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</p>', '\n\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def send_verification_email(email, name, code):
    digits = list(code)
    expiry = current_app.config.get('VERIFICATION_CODE_EXPIRY_MINUTES', 2)
    plain = (
        f'Hi {name},\n\n'
        f'Your CareerPearls verification code is: {code}\n\n'
        f'Enter this 6-digit code on the verification page. It expires in {expiry} minutes.\n\n'
        f'If you did not register, ignore this email.\n\n'
        f'— CareerPearls'
    )
    ok, err = send_email(
        f'{code} — Your CareerPearls verification code',
        [email],
        'verification_code.html',
        plain_body=plain,
        name=name,
        code=code,
        digits=digits,
        expiry_minutes=expiry,
    )
    return ok, err


def send_welcome_email(user):
    ok, _ = send_email(
        'Welcome to CareerPearls!',
        [user.email],
        'welcome.html',
        plain_body=(
            f'Hi {user.name},\n\nWelcome to CareerPearls! Visit '
            f'{current_app.config.get("APP_BASE_URL", "http://127.0.0.1:5000")} to get started.\n'
        ),
        user=user,
    )
    return ok


def send_password_reset_email(user, token):
    base = current_app.config.get('APP_BASE_URL', 'http://127.0.0.1:5000')
    reset_url = f'{base}/reset-password/{token}'
    ok, _ = send_email(
        'Reset Your CareerPearls Password',
        [user.email],
        'password_reset.html',
        plain_body=f'Hi {user.name},\n\nReset your password: {reset_url}\n\nThis link expires in 1 hour.\n',
        user=user,
        reset_url=reset_url,
    )
    return ok


def send_password_reset_code_email(email, name, code):
    digits = list(code)
    expiry = current_app.config.get('VERIFICATION_CODE_EXPIRY_MINUTES', 2)
    plain = (
        f'Hi {name},\n\n'
        f'Your CareerPearls password reset code is: {code}\n\n'
        f'Enter this 6-digit code on the website to reset your password. It expires in {expiry} minutes.\n\n'
        f'If you did not request a password reset, please ignore this email.\n\n'
        f'— CareerPearls'
    )
    ok, err = send_email(
        f'{code} — Your Password Reset Code',
        [email],
        'verification_code.html',
        plain_body=plain,
        name=name,
        code=code,
        digits=digits,
        expiry_minutes=expiry,
    )
    return ok, err


def _format_date_with_day(date_val):
    if not date_val:
        return ''
    if isinstance(date_val, datetime):
        return date_val.strftime('%A, %b %d, %Y')
    s = str(date_val).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime('%A, %b %d, %Y')
        except ValueError:
            continue
    return s


def send_interview_call_email(candidate_email, candidate_name, company_name, job_title, interview_date, interview_time, interview_location, message_text='', company_email=''):
    """
    Send official Interview Invitation email.
    """
    formatted_date = _format_date_with_day(interview_date)
    subject = f"Interview Invitation: {job_title} — {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"Interview Invitation: {job_title} at {company_name}\n\n"
        f"• Date & Day: {formatted_date}\n"
        f"• Time: {interview_time}\n"
        f"• Venue / Link: {interview_location}\n\n"
        f"Best regards,\n{company_name} Hiring Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'interview_call.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        interview_date=formatted_date,
        interview_time=interview_time,
        interview_location=interview_location,
        message_text=message_text,
        company_email=company_email,
    )
    return ok, err


def send_interview_modified_email(candidate_email, candidate_name, company_name, job_title, interview_date, interview_time, interview_location, message_text='', company_email=''):
    """
    Send official Interview Schedule Updated email.
    """
    formatted_date = _format_date_with_day(interview_date)
    subject = f"Interview Schedule Updated: {job_title} — {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"Your interview schedule has been updated: {job_title} at {company_name}\n\n"
        f"• Revised Date & Day: {formatted_date}\n"
        f"• Revised Time: {interview_time}\n"
        f"• Venue / Link: {interview_location}\n\n"
        f"Note from Employer:\n{message_text or 'Please take note of the updated interview schedule.'}\n\n"
        f"Best regards,\n{company_name} Hiring Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'interview_modified.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        interview_date=formatted_date,
        interview_time=interview_time,
        interview_location=interview_location,
        message_text=message_text,
        company_email=company_email,
    )
    return ok, err


def send_application_rejection_email(candidate_email, candidate_name, company_name, job_title, reason=''):
    """
    Send initial Application Rejection email (before interview).
    """
    subject = f"Application Status: {job_title} — {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"Thank you for applying for the {job_title} position at {company_name}.\n\n"
        f"After careful consideration of all applications, we have decided to proceed with other candidates whose background more closely matches our immediate requirements.\n\n"
        f"Remarks / Reason: {reason or 'Candidate profile review concluded.'}\n\n"
        f"We appreciate your interest and wish you the best in your job search.\n\n"
        f"Best regards,\n{company_name} Recruitment Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'application_rejected.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        reason=reason,
    )
    return ok, err


def send_contact_email(name, email, phone, message):
    recipient = 'career.pulse.web@gmail.com'
    subject = f"New Contact Message from {name}"
    plain = (
        f"New Contact Message Received:\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Phone: {phone}\n\n"
        f"Message:\n{message}\n"
    )
    ok, err = send_email(
        subject,
        [recipient],
        'contact_notification.html',
        plain_body=plain,
        name=name,
        email=email,
        phone=phone,
        message=message,
    )
    return ok, err


def send_direct_employer_email(candidate_email, candidate_name, company_name, employer_name, subject, message_body, job_title=''):
    """
    Send a direct email from employer to candidate for audit purposes.
    """
    import re
    cleaned_body = message_body.strip() if message_body else ''
    # Strip any duplicate trailing Best regards / Regards from message text
    cleaned_body = re.sub(r'(?:\r?\n)+\s*(?:Best\s+[Rr]egards|Warm\s+[Rr]egards|[Rr]egards|[Tt]hanks\s+&?\s*[Rr]egards)[\s\S]*$', '', cleaned_body, flags=re.IGNORECASE).strip()

    full_subject = subject.strip()
    plain = (
        f"Subject: {subject}\n\n"
        f"Message:\n{cleaned_body}\n\n"
        f"You may reply directly to this email.\n\n"
        f"Best regards,\n{employer_name} · {company_name}"
    )
    ok, err = send_email(
        full_subject,
        [candidate_email],
        'direct_message.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        employer_name=employer_name,
        email_subject=subject,
        message_body=cleaned_body,
        job_title=job_title,
    )
    return ok, err


def send_complaint_confirmation_email(complainant_email, complainant_name, ticket_id, category, subject_text, description=''):
    subject = f"Complaint Registered: {ticket_id} — CareerPearls"
    desc_content = description if description else subject_text
    plain = (
        f"Hi {complainant_name or 'User'},\n\n"
        f"Thank you for reporting this issue to CareerPearls Trust & Safety team.\n\n"
        f"Complaint Ticket ID: {ticket_id}\n"
        f"Category: {category}\n"
        f"Subject: {subject_text}\n"
        f"Description:\n{desc_content}\n\n"
        f"Status: Pending Admin Review\n\n"
        f"Our team investigates every report thoroughly to keep the CareerPearls platform safe and transparent. "
        f"You will receive an update once your complaint has been reviewed.\n\n"
        f"Best regards,\nCareerPearls Trust & Safety Team"
    )
    ok, err = send_email(
        subject,
        [complainant_email],
        'complaint_confirmation.html',
        plain_body=plain,
        complainant_name=complainant_name,
        ticket_id=ticket_id,
        category=category,
        subject_text=subject_text,
        description=desc_content,
    )
    return ok, err


def send_complaint_status_update_email(complainant_email, complainant_name, ticket_id, new_status, admin_note='', category='', subject_text='', description=''):
    subject = f"Complaint Update: {ticket_id} is {new_status} — CareerPearls"
    plain = (
        f"Hi {complainant_name or 'User'},\n\n"
        f"Your complaint {ticket_id} status has been updated to: {new_status}.\n\n"
        f"Admin Resolution Note:\n{admin_note if admin_note else 'No additional remarks.'}\n\n"
        f"Thank you for helping us keep CareerPearls a safe and authentic job marketplace.\n\n"
        f"Best regards,\nCareerPearls Trust & Safety Team"
    )
    ok, err = send_email(
        subject,
        [complainant_email],
        'complaint_status_update.html',
        plain_body=plain,
        complainant_name=complainant_name,
        ticket_id=ticket_id,
        new_status=new_status,
        admin_note=admin_note,
        category=category,
        subject_text=subject_text,
        description=description,
    )
    return ok, err


def send_shortlisted_email(candidate_email, candidate_name, company_name, job_title, company_email=''):
    """
    Send official shortlisted email notification to candidate.
    """
    subject = f"Application Shortlisted: {job_title} — {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"We are pleased to inform you that your application for the "
        f"{job_title} role at {company_name} has been shortlisted.\n\n"
        f"Our talent team was impressed by your qualifications. "
        f"We will be reaching out shortly with details regarding the next steps in the recruitment process.\n\n"
        f"For any queries, please feel free to email our hiring team at: {company_email or 'support@careerpearls.com'}\n\n"
        f"Best regards,\n{company_name} Hiring Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'shortlisted.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        company_email=company_email,
    )
    return ok, err


def send_candidate_hired_email(candidate_email, candidate_name, company_name, job_title, employer_name='', company_email='', salary_offered=''):
    """
    Send official Job Offer / Hired email notification to candidate.
    """
    subject = f"Job Offer: {job_title} — {company_name}"
    salary_line = f"Offered Compensation: {salary_offered}\n\n" if salary_offered else ""
    plain = (
        f"Dear {candidate_name},\n\n"
        f"Congratulations! Following your interview evaluation, {company_name} is extending an employment offer for the {job_title} position.\n\n"
        f"{salary_line}"
        f"What happens next:\n"
        f"You will receive your next email within a few days containing your onboarding paperwork, official contract, and job starting date.\n\n"
        f"For any questions, feel free to contact our recruitment team at: {company_email or 'support@careerpearls.com'}\n\n"
        f"Welcome to the team!\n\n"
        f"Best regards,\n{company_name} Hiring Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'candidate_hired.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        employer_name=employer_name,
        company_email=company_email,
        salary_offered=salary_offered,
    )
    return ok, err


def send_interview_failed_email(candidate_email, candidate_name, company_name, job_title, reason='', company_email=''):
    """
    Send post-interview evaluation update email (Thank you for coming).
    """
    subject = f"Interview Update: {job_title} — {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"Thank you for taking the time to interview with {company_name} for the {job_title} position.\n\n"
        f"We truly appreciate your time and effort. While our team was impressed with your credentials, we have decided to move forward with other candidates for this role at this time.\n\n"
        f"Evaluation Remarks: {reason or 'Interview process concluded.'}\n\n"
        f"We wish you the very best of luck in your career search and future opportunities.\n\n"
        f"Best regards,\n{company_name} Hiring Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'interview_failed.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        reason=reason,
        company_email=company_email,
    )
    return ok, err


def send_interview_rescheduled_email(candidate_email, candidate_name, company_name, job_title, employer_name='', company_email=''):
    """
    Send official Interview Rescheduled notice email to candidate.
    """
    subject = f"Interview Rescheduled: {job_title} — {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"We are rescheduling your interview for the {job_title} position at {company_name}.\n\n"
        f"You will receive an email soon with your updated interview schedule, date, and time details.\n\n"
        f"If you have any questions or scheduling preferences, please reply to our hiring team at: {company_email or 'support@careerpearls.com'}\n\n"
        f"Thank you for your patience and understanding.\n\n"
        f"Best regards,\n{company_name} Hiring Team\nCareerPearls"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'interview_rescheduled.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        employer_name=employer_name,
        company_email=company_email,
    )
    return ok, err


def send_interview_reminder_email(candidate_email, candidate_name, company_name, job_title, interview_date, interview_time, interview_location, interview_mode='On-Site'):
    """
    Send automated 24-hour Interview Reminder email to candidate from CareerPearls.
    """
    formatted_date = _format_date_with_day(interview_date)
    subject = f"Interview Reminder: {job_title} with {company_name}"
    plain = (
        f"Dear {candidate_name},\n\n"
        f"This is a friendly reminder from CareerPearls that your upcoming interview for {job_title} at {company_name} is scheduled for tomorrow.\n\n"
        f"• Position: {job_title}\n"
        f"• Company: {company_name}\n"
        f"• Date & Day: {formatted_date}\n"
        f"• Time: {interview_time}\n"
        f"• Mode: {interview_mode}\n"
        f"• Venue / Link: {interview_location or 'Corporate Office'}\n\n"
        f"Please be available and prepared 5 to 10 minutes prior to the scheduled time.\n\n"
        f"Best regards,\nCareerPearls Team"
    )
    ok, err = send_email(
        subject,
        [candidate_email],
        'interview_reminder.html',
        plain_body=plain,
        candidate_name=candidate_name,
        company_name=company_name,
        job_title=job_title,
        interview_date=formatted_date,
        interview_time=interview_time,
        interview_location=interview_location,
        interview_mode=interview_mode,
    )
    return ok, err



