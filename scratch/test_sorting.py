import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")

from app import create_app, db
from app.models import User, Candidate, Job, Application, Interview, Message, AuditLog, Complaint, SavedJob, Company

app = create_app()

with app.app_context():
    print("=== Testing Database Model Query Sorting ===")
    
    # 1. Users
    users = User.query.order_by(User.created_at.desc()).limit(3).all()
    print("Latest 3 Users created_at:")
    for u in users:
        print("  -", u.email, u.created_at)
        
    # 2. Jobs
    jobs = Job.query.order_by(Job.created_at.desc()).limit(3).all()
    print("\nLatest 3 Jobs created_at:")
    for j in jobs:
        print("  -", j.title, j.created_at)

    # 3. Applications
    apps = Application.query.order_by(Application.applied_at.desc()).limit(3).all()
    print("\nLatest 3 Applications applied_at:")
    for a in apps:
        print("  - App ID:", a.id, "Applied At:", a.applied_at)

    # 4. Messages
    msgs = Message.query.order_by(Message.sent_at.desc()).limit(3).all()
    print("\nLatest 3 Messages sent_at:")
    for m in msgs:
        print("  - Msg ID:", m.id, "Sent At:", m.sent_at)

    # 5. Audit Logs
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(3).all()
    print("\nLatest 3 Audit Logs created_at:")
    for l in logs:
        print("  - Action:", l.action, "Created At:", l.created_at)
