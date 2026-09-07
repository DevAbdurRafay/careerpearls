import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")
from app import create_app, db

app = create_app()
with app.app_context():
    res = db.session.execute(db.text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='candidates' AND column_name='job_notifier_enabled';")).fetchall()
    print("Column in PostgreSQL DB:", res)
