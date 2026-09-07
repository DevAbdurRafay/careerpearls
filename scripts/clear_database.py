"""Script to clear all users and jobs from the CareerPearls database."""

import sys
import os

# Add the parent directory to the path so we can import the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User, Job, Candidate, Recruiter, Company

def clear_database():
    """Delete all users and jobs from the database."""
    app = create_app()
    
    with app.app_context():
        print("Starting database cleanup...")
        
        # Delete all jobs first
        job_count = Job.query.count()
        print(f"Deleting {job_count} jobs...")
        Job.query.delete()
        
        # Delete all candidates
        candidate_count = Candidate.query.count()
        print(f"Deleting {candidate_count} candidates...")
        Candidate.query.delete()
        
        # Delete all recruiters
        recruiter_count = Recruiter.query.count()
        print(f"Deleting {recruiter_count} recruiters...")
        Recruiter.query.delete()
        
        # Delete all companies
        company_count = Company.query.count()
        print(f"Deleting {company_count} companies...")
        Company.query.delete()
        
        # Delete all users
        user_count = User.query.count()
        print(f"Deleting {user_count} users...")
        User.query.delete()
        
        # Commit the changes
        db.session.commit()
        
        print("Database cleanup completed successfully!")
        print(f"Deleted {job_count} jobs, {candidate_count} candidates, {recruiter_count} recruiters, {company_count} companies, and {user_count} users.")

if __name__ == '__main__':
    # Ask for confirmation
    print("WARNING: This will delete ALL users and jobs from the database!")
    print("This action cannot be undone.")
    print("Proceeding with cleanup...")
    
    clear_database()
