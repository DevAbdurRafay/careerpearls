"""Mock data manager for local testing - provides fallback data when database is not fully set up."""

from flask import session, current_app
from flask_login import current_user
from datetime import datetime, timedelta
import random


class MockDataManager:
    """Provides mock data for local testing when database relationships are missing."""
    
    @staticmethod
    def get_mock_candidate():
        """Return mock candidate data for local testing."""
        return {
            'id': 1,
            'full_name': 'Test Candidate',
            'phone': '+92 3001234567',
            'location': 'Karachi, Pakistan',
            'headline': 'Full Stack Developer | Python & React Specialist',
            'availability': 'Immediately Available',
            'work_mode': 'Remote',
            'bio': 'Experienced developer with 5+ years in web development.',
            'has_internship': True,
            'internship_details': '3-month internship at Tech Corp',
            'profile_image': '',
            'career_status': 'Experienced',
            'onboarding_complete': True,
            'linkedin_url': 'https://linkedin.com/in/test',
            'github_url': 'https://github.com/test',
            'portfolio_url': 'https://test.com',
        }
    
    @staticmethod
    def get_mock_company():
        """Return mock company data for local testing."""
        return {
            'id': 1,
            'name': 'TechCorp Solutions',
            'industry': 'Technology',
            'domain': 'techcorp.com',
            'website': 'https://techcorp.com',
            'description': 'Leading technology company',
            'working_since_months': 64,  # 5 years 4 months
            'is_verified': True,
            'verification_status': 'Approved',
            'logo_path': '',
            'phone': '+92 21 1234567',
            'ntn_id': '1234567',
        }
    
    @staticmethod
    def get_mock_jobs():
        """Return mock job listings for local testing."""
        return [
            {
                'id': 1,
                'title': 'Senior Python Developer',
                'category': 'Engineering',
                'description': 'Looking for experienced Python developer...',
                'location': 'Remote',
                'salary_range': 'PKR 150,000 - 250,000',
                'employment_type': 'Full-time',
                'experience_required': '3-5 years',
                'status': 'active',
                'closes_at': datetime.utcnow() + timedelta(days=30),
                'posted_at': datetime.utcnow() - timedelta(days=5),
            },
            {
                'id': 2,
                'title': 'Frontend React Developer',
                'category': 'Engineering',
                'description': 'React developer needed for exciting project...',
                'location': 'Karachi',
                'salary_range': 'PKR 100,000 - 180,000',
                'employment_type': 'Full-time',
                'experience_required': '2-4 years',
                'status': 'active',
                'closes_at': datetime.utcnow() + timedelta(days=25),
                'posted_at': datetime.utcnow() - timedelta(days=10),
            },
        ]
    
    @staticmethod
    def get_mock_applications():
        """Return mock job applications for local testing."""
        return [
            {
                'id': 1,
                'job_id': 1,
                'candidate_id': 1,
                'status': 'Under Review',
                'applied_at': datetime.utcnow() - timedelta(days=2),
                'cover_letter': 'I am excited to apply for this position...',
            },
            {
                'id': 2,
                'job_id': 2,
                'candidate_id': 1,
                'status': 'Interview Scheduled',
                'applied_at': datetime.utcnow() - timedelta(days=5),
                'cover_letter': 'My experience matches your requirements...',
            },
        ]
    
    @staticmethod
    def get_mock_education():
        """Return mock education data."""
        return [
            {
                'id': 1,
                'institution': 'University of Karachi',
                'degree': 'BS Computer Science',
                'field_of_study': 'Computer Science',
                'is_current': False,
                'start_date': datetime(2016, 1, 1),
                'end_date': datetime(2020, 1, 1),
            }
        ]
    
    @staticmethod
    def get_mock_skills():
        """Return mock skills data."""
        return [
            {'id': 1, 'skill_name': 'Python', 'proficiency_level': 'Expert'},
            {'id': 2, 'skill_name': 'JavaScript', 'proficiency_level': 'Advanced'},
            {'id': 3, 'skill_name': 'React', 'proficiency_level': 'Advanced'},
            {'id': 4, 'skill_name': 'SQL', 'proficiency_level': 'Intermediate'},
        ]
    
    @staticmethod
    def get_mock_certifications():
        """Return mock certifications data."""
        return [
            {
                'id': 1,
                'title': 'AWS Certified Developer',
                'issuing_organization': 'Amazon Web Services',
                'issue_year': '2022',
                'credential_id': 'AWS-12345',
                'credential_url': 'https://aws.amazon.com/verify',
                'description': 'Associate level certification',
                'file_path': '',
            }
        ]
    
    @staticmethod
    def is_testing_mode():
        """Check if application is in testing mode."""
        return current_app.config.get('TESTING_MODE', False)
    
    @staticmethod
    def safe_getattr(obj, attr, default=''):
        """Safely get attribute from object with fallback."""
        if obj is None:
            return default
        try:
            return getattr(obj, attr, default)
        except (AttributeError, TypeError):
            return default


def get_mock_candidate_view():
    """Get a mock candidate view object for template rendering."""
    from app.candidate.onboarding_store import SessionCandidateView
    return SessionCandidateView()


def ensure_mock_session_data():
    """Ensure session has mock data for testing mode."""
    if not MockDataManager.is_testing_mode():
        return
    
    # Initialize mock data in session if not present
    if 'mock_candidate' not in session:
        session['mock_candidate'] = MockDataManager.get_mock_candidate()
    
    if 'mock_company' not in session:
        session['mock_company'] = MockDataManager.get_mock_company()
    
    if 'mock_jobs' not in session:
        session['mock_jobs'] = MockDataManager.get_mock_jobs()
    
    if 'mock_applications' not in session:
        session['mock_applications'] = MockDataManager.get_mock_applications()
    
    session.modified = True