import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")

from app import create_app
from app.models import Candidate, User

app = create_app()

with app.app_context():
    try:
        cand = Candidate.query.first()
        if cand:
            print("SUCCESS: Candidate query executed cleanly!")
            print("Candidate ID:", cand.id, "| Name:", cand.full_name, "| Job Notifier Enabled:", getattr(cand, 'job_notifier_enabled', None))
        else:
            print("SUCCESS: Candidate query executed cleanly (no candidates in DB).")
    except Exception as e:
        import traceback
        print("ERROR:", e)
        traceback.print_exc()
