import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")

from app import create_app, db

app = create_app()

with app.app_context():
    try:
        print("Executing PostgreSQL column migration for candidates.job_notifier_enabled...")
        db.session.execute(db.text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS job_notifier_enabled BOOLEAN DEFAULT TRUE;"))
        db.session.commit()
        print("SUCCESS: candidates.job_notifier_enabled column added successfully to PostgreSQL database!")
    except Exception as e:
        db.session.rollback()
        print("Migration error:", e)
        # Try without IF NOT EXISTS if needed
        try:
            db.session.execute(db.text("ALTER TABLE candidates ADD COLUMN job_notifier_enabled BOOLEAN DEFAULT TRUE;"))
            db.session.commit()
            print("SUCCESS on 2nd attempt: candidates.job_notifier_enabled added!")
        except Exception as e2:
            db.session.rollback()
            print("Migration 2nd attempt error:", e2)
