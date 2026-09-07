import pytest
from app.models import Candidate, CandidateCertification, db

def test_candidate_profile_completion_pct(app):
    with app.app_context():
        c = Candidate(
            user_id=999,
            full_name="Jane Doe",
            phone="+92 3001234567",
            location="Karachi",
            headline="Software Engineer",
            availability="immediate",
            work_mode="remote",
            has_internship=True,
            profile_image="photo.jpg"
        )
        # Without edu and skills -> 8 out of 10 checks filled = 80%
        assert c.calculate_completion_pct() == 80


def test_candidate_certification_model(app):
    with app.app_context():
        cert = CandidateCertification(
            candidate_id=1,
            title="AWS Certified Cloud Practitioner",
            issuing_organization="Amazon Web Services",
            issue_year="2024",
            description="Cloud Architecture Essentials",
            file_path="aws_cert.pdf"
        )
        assert cert.title == "AWS Certified Cloud Practitioner"
        assert cert.description == "Cloud Architecture Essentials"
        assert cert.file_path == "aws_cert.pdf"
