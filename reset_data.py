from app import create_app, db
from app.models import Job, JobSkill, Application, Interview, Offer, SavedJob, Shortlist, ApplicationStatusHistory, Message, Complaint

app = create_app()
with app.app_context():
    print("1. Clearing Offers...")
    Offer.query.delete()

    print("2. Clearing Interviews...")
    Interview.query.delete()

    print("3. Clearing Application Status History...")
    ApplicationStatusHistory.query.delete()

    print("4. Clearing Application-linked Messages...")
    Message.query.filter(Message.application_id.isnot(None)).delete(synchronize_session=False)

    print("5. Clearing Applications...")
    Application.query.delete()

    print("6. Clearing Saved Jobs, Shortlists & Job Complaints...")
    SavedJob.query.delete()
    Shortlist.query.delete()
    Complaint.query.filter(Complaint.against_job_id.isnot(None)).delete(synchronize_session=False)

    print("7. Clearing Job Skills & Jobs...")
    JobSkill.query.delete()
    Job.query.delete()

    db.session.commit()
    print("SUCCESS: 0 Jobs, 0 Applications, 0 Hired Records remaining! Database is fully refreshed.")
