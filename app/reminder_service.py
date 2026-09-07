import logging
import threading
import time
from datetime import datetime, timedelta
from app.extensions import db
from app.models import Interview, Application, Job, User, Candidate
from app.email_utils import send_interview_reminder_email

logger = logging.getLogger(__name__)


def process_interview_reminders(app=None):
    """
    Finds all active scheduled interviews happening within 24 hours from now
    that haven't had a reminder sent yet, and sends the candidate an official
    reminder email from CareerPearls.
    """
    def _execute():
        now = datetime.utcnow()
        # Remind candidate 1 day (24 hours) prior to interview time
        reminder_window_end = now + timedelta(hours=24, minutes=15)
        
        due_interviews = (
            Interview.query
            .filter(
                Interview.status == 'Scheduled',
                Interview.reminder_sent == False,
                Interview.scheduled_at > now,
                Interview.scheduled_at <= reminder_window_end
            )
            .all()
        )

        sent_count = 0
        for interview in due_interviews:
            try:
                application = interview.application
                if not application or not application.job or not application.candidate:
                    continue

                candidate = application.candidate
                cand_user = candidate.user
                cand_email = (cand_user.email if cand_user else None) or candidate.email
                cand_name = candidate.full_name or (cand_user.name if cand_user else 'Candidate')

                job = application.job
                job_title = job.title or 'Position'
                company_name = job.company.name if (job.company and job.company.name) else 'Employer'

                interview_date = interview.scheduled_at.strftime('%Y-%m-%d')
                interview_time = interview.scheduled_at.strftime('%I:%M %p')
                interview_location = interview.location_or_link or 'Corporate Office'
                interview_mode = interview.mode or 'On-Site'

                if cand_email:
                    ok, err = send_interview_reminder_email(
                        candidate_email=cand_email,
                        candidate_name=cand_name,
                        company_name=company_name,
                        job_title=job_title,
                        interview_date=interview_date,
                        interview_time=interview_time,
                        interview_location=interview_location,
                        interview_mode=interview_mode,
                    )
                    if ok:
                        interview.reminder_sent = True
                        db.session.commit()
                        sent_count += 1
                        logger.info(f"[Interview Reminder] Sent reminder to {cand_email} for interview {interview.id}")
                    else:
                        logger.error(f"[Interview Reminder] Failed to send reminder to {cand_email}: {err}")
            except Exception as ex:
                logger.error(f"[Interview Reminder] Error processing interview {interview.id}: {ex}")
                db.session.rollback()

        return sent_count

    if app:
        with app.app_context():
            return _execute()
    else:
        return _execute()


def start_reminder_scheduler(app):
    """
    Starts a background daemon thread that periodically checks and dispatches
    interview reminders every 15 minutes.
    """
    # Prevent running duplicate threads in Flask reload child processes
    import os
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return

    def _run_scheduler():
        logger.info("[Interview Reminder] Background reminder worker started.")
        while True:
            try:
                with app.app_context():
                    process_interview_reminders()
            except Exception as e:
                logger.error(f"[Interview Reminder Scheduler] Error: {e}")
            time.sleep(900)  # Check every 15 minutes

    thread = threading.Thread(target=_run_scheduler, daemon=True, name="InterviewReminderWorker")
    thread.start()
