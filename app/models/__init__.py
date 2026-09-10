"""All SQLAlchemy models for CareerPearls — single consolidated schema file."""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, login_manager

APPLICATION_STATUSES = [
    'Under Review', 'Interview Scheduled', 'Selected', 'Rejected',
    'Contacted', 'Applied', 'Screening', 'Shortlisted', 'Interview', 'Withdrawn',
]


# ---------------------------------------------------------------------------
# User & Auth
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=True)  # null for OAuth-only users
    oauth_provider = db.Column(db.String(30), nullable=True)
    oauth_id = db.Column(db.String(120), nullable=True)  # Google subject / google_id
    google_id = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='candidate')
    role_id = db.Column(db.BigInteger, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    approval_status = db.Column(db.String(20), default='approved', nullable=False)
    approval_note = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    privacy_policy_accepted_at = db.Column(db.DateTime, nullable=True)
    theme_mode = db.Column(db.String(10), default='light', nullable=False)
    accent_color = db.Column(db.String(15), default='purple', nullable=False)

    candidate = db.relationship('Candidate', backref='user', uselist=False, foreign_keys='Candidate.user_id', cascade='all, delete-orphan')
    recruiter = db.relationship('Recruiter', backref='user', uselist=False, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def is_candidate(self):
        return self.role == 'candidate'

    def is_employer(self):
        return self.role == 'employer'

    def is_admin(self):
        return self.role == 'admin'

    def needs_oauth_onboarding(self):
        return self.role == 'pending'

    def is_approved(self):
        return self.role == 'admin' or (self.role in ('candidate', 'employer') and self.approval_status == 'approved')

    def is_pending_approval(self):
        return self.role in ('candidate', 'employer') and self.approval_status == 'pending'

    def is_rejected(self):
        return self.approval_status == 'rejected'


class EmailVerification(db.Model):
    """Pending registration — 6-digit code, expires in 2 minutes."""
    __tablename__ = 'email_verifications'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    code_hash = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

class Candidate(db.Model):
    __tablename__ = 'candidates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    location = db.Column(db.String(120))
    headline = db.Column(db.String(200))
    availability = db.Column(db.String(50))
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(255))
    profile_photo_path = db.synonym('profile_image')
    career_status = db.Column(db.String(50))
    work_mode = db.Column(db.String(30))
    has_internship = db.Column(db.Boolean, nullable=True)
    internship_details = db.Column(db.String(500))
    github_url = db.Column(db.String(255))
    linkedin_url = db.Column(db.String(255))
    kaggle_url = db.Column(db.String(255))
    portfolio_url = db.Column(db.String(255))
    is_location_verified = db.Column(db.Boolean, default=False, nullable=False)
    location_verified_at = db.Column(db.DateTime, nullable=True)
    location_verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    onboarding_complete = db.Column(db.Boolean, default=False, nullable=False)
    job_notifier_enabled = db.Column(db.Boolean, default=True, nullable=False)

    skills = db.relationship('CandidateSkill', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    interests = db.relationship('CandidateInterest', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    education = db.relationship('CandidateEducation', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    experience = db.relationship('CandidateExperience', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    resumes = db.relationship('Resume', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    certifications = db.relationship('CandidateCertification', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    saved_jobs = db.relationship('SavedJob', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')

    def calculate_completion_pct(self):
        try:
            edu_rel = self.education
            edu_count = edu_rel.count() if callable(getattr(edu_rel, 'count', None)) else len(edu_rel or [])
        except Exception:
            edu_count = 0
        try:
            skills_rel = self.skills
            skills_count = skills_rel.count() if callable(getattr(skills_rel, 'count', None)) else len(skills_rel or [])
        except Exception:
            skills_count = 0
        checks = [
            bool(self.full_name and self.full_name.strip()),
            bool(self.phone and self.phone.strip()),
            bool(self.location and self.location.strip()),
            bool(self.headline and self.headline.strip()),
            bool(self.availability and self.availability.strip()),
            bool(self.work_mode and self.work_mode.strip()),
            self.has_internship is not None,
            bool(self.profile_image and self.profile_image.strip()),
            edu_count > 0,
            skills_count > 0,
        ]
        completed = sum(1 for c in checks if c)
        return int((completed / len(checks)) * 100)


class CandidateSkill(db.Model):
    __tablename__ = 'candidate_skills'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    skill_name = db.Column(db.String(80), nullable=False)
    proficiency_level = db.Column(db.String(30))


class CandidateInterest(db.Model):
    __tablename__ = 'candidate_interests'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    interest_name = db.Column(db.String(80), nullable=False)

    __table_args__ = (db.UniqueConstraint('candidate_id', 'interest_name', name='uq_candidate_interest'),)


CAREER_STATUS_OPTIONS = [
    ('student', 'Student — currently studying'),
    ('graduate', 'Recent Graduate — looking for first role'),
    ('professional', 'Working Professional — exploring new opportunities'),
    ('switcher', 'Career Switcher — changing field or industry'),
    ('freelancer', 'Freelancer — independent or contract work'),
    ('intern', 'Internship Seeker — looking for internship'),
]

# Shared field list — used for candidate interests AND employer hiring categories
FIELD_OPTIONS = [
    'Software Development', 'Web Development', 'Mobile Apps', 'Data Science',
    'Data Analysis', 'Machine Learning', 'UI/UX Design', 'Graphic Design',
    'Interior Design', 'AutoCAD', 'Civil Engineering', 'Mechanical Engineering',
    'Electrical Engineering', 'Architecture', 'BIM & 3D Modeling',
    'Digital Marketing', 'Content Writing', 'Project Management', 'Business Analysis',
    'Finance', 'Human Resources', 'Sales', 'Customer Support', 'DevOps',
    'Cybersecurity', 'Cloud Computing', 'Product Management', 'Quality Assurance',
    'Education', 'Healthcare', 'Engineering', 'Legal', 'Consulting',
    'Supply Chain', 'Manufacturing', 'Automotive', 'Construction',
    'Fashion Design', 'Video Production', 'Photography', 'Research',
]

PREDEFINED_SKILLS = [
    'Python', 'JavaScript', 'TypeScript', 'React.js', 'Next.js', 'Vue.js', 'Angular',
    'Node.js', 'Express.js', 'Flask', 'Django', 'FastAPI', 'HTML5', 'CSS3', 'Tailwind CSS',
    'Bootstrap', 'Sass', 'REST API', 'GraphQL', 'SQL', 'PostgreSQL', 'MySQL', 'SQLite',
    'MongoDB', 'Redis', 'Docker', 'Kubernetes', 'AWS', 'Google Cloud (GCP)', 'Azure',
    'Git', 'GitHub', 'GitLab', 'CI/CD', 'Linux', 'Bash', 'C', 'C++', 'C#', '.NET',
    'Java', 'Spring Boot', 'Kotlin', 'Swift', 'Flutter', 'React Native', 'Android Development',
    'iOS Development', 'Go (Golang)', 'Rust', 'PHP', 'Laravel', 'WordPress', 'Figma',
    'Adobe XD', 'Photoshop', 'Illustrator', 'UI/UX Research', 'Wireframing', 'Prototyping',
    'SEO', 'SEM', 'Social Media Marketing', 'Google Analytics', 'Content Strategy',
    'Copywriting', 'Technical Writing', 'Data Analysis', 'Pandas', 'NumPy', 'Scikit-Learn',
    'TensorFlow', 'PyTorch', 'Power BI', 'Tableau', 'Excel', 'Statistics', 'Project Management',
    'Agile', 'Scrum', 'Jira', 'Trello', 'Asana', 'Communication', 'Leadership', 'Problem Solving',
    'Time Management', 'Customer Support', 'Salesforce', 'HubSpot', 'Accounting', 'Financial Analysis',
]


WORK_MODE_OPTIONS = [
    ('on_site', 'On-site / In-office'),
    ('remote', 'Remote'),
    ('hybrid', 'Hybrid'),
]

AVAILABILITY_OPTIONS = [
    ('immediate', 'Immediate (Available to start right away)'),
    ('2_weeks', '2 Weeks Notice'),
    ('1_month', '1 Month Notice'),
    ('part_time', 'Part-Time / Flexible Hours'),
    ('internship_summer', 'Internship (Summer 2026)'),
    ('internship_fall', 'Internship (Fall / Winter 2026)'),
    ('contract', 'Contract / Project-based'),
]

# World country dial codes with flags (excluding Israel)
COUNTRY_CODES = [
    ('+92', '🇵🇰 Pakistan (+92)'),
    ('+1', '🇺🇸 / 🇨🇦 USA / Canada (+1)'),
    ('+44', '🇬🇧 United Kingdom (+44)'),
    ('+971', '🇦🇪 United Arab Emirates (+971)'),
    ('+966', '🇸🇦 Saudi Arabia (+966)'),
    ('+91', '🇮🇳 India (+91)'),
    ('+61', '🇦🇺 Australia (+61)'),
    ('+49', '🇩🇪 Germany (+49)'),
    ('+33', '🇫🇷 France (+33)'),
    ('+81', '🇯🇵 Japan (+81)'),
    ('+86', '🇨🇳 China (+86)'),
    ('+65', '🇸🇬 Singapore (+65)'),
    ('+60', '🇲🇾 Malaysia (+60)'),
    ('+90', '🇹🇷 Turkey (+90)'),
    ('+974', '🇶🇦 Qatar (+974)'),
    ('+965', '🇰🇼 Kuwait (+965)'),
    ('+968', '🇴🇲 Oman (+968)'),
    ('+973', '🇧🇭 Bahrain (+973)'),
    ('+20', '🇪🇬 Egypt (+20)'),
    ('+27', '🇿🇦 South Africa (+27)'),
    ('+55', '🇧🇷 Brazil (+55)'),
    ('+39', '🇮🇹 Italy (+39)'),
    ('+34', '🇪🇸 Spain (+34)'),
    ('+31', '🇳🇱 Netherlands (+31)'),
    ('+41', '🇨🇭 Switzerland (+41)'),
    ('+46', '🇸🇪 Sweden (+46)'),
    ('+47', '🇳🇴 Norway (+47)'),
    ('+45', '🇩🇰 Denmark (+45)'),
    ('+353', '🇮🇪 Ireland (+353)'),
    ('+64', '🇳🇿 New Zealand (+64)'),
    ('+82', '🇰🇷 South Korea (+82)'),
    ('+63', '🇵🇭 Philippines (+63)'),
    ('+62', '🇮🇩 Indonesia (+62)'),
    ('+84', '🇻🇳 Vietnam (+84)'),
    ('+880', '🇧🇩 Bangladesh (+880)'),
    ('+94', '🇱🇰 Sri Lanka (+94)'),
    ('+977', '🇳🇵 Nepal (+977)'),
    ('+234', '🇳🇬 Nigeria (+234)'),
    ('+254', '🇰🇪 Kenya (+254)'),
    ('+52', '🇲🇽 Mexico (+52)'),
    ('+54', '🇦🇷 Argentina (+54)'),
]


INTEREST_OPTIONS = FIELD_OPTIONS  # alias for backward compatibility

ORGANIZATION_TYPE_OPTIONS = [
    ('startup', 'Startup'),
    ('sme', 'Small & Medium Business'),
    ('enterprise', 'Enterprise / Corporation'),
    ('agency', 'Recruitment Agency'),
    ('nonprofit', 'Non-Profit Organization'),
    ('government', 'Government / Public Sector'),
]

COMPANY_SIZE_OPTIONS = [
    ('1-10', '1–10 employees'),
    ('11-50', '11–50 employees'),
    ('51-200', '51–200 employees'),
    ('201-500', '201–500 employees'),
    ('500+', '500+ employees'),
]

EMPLOYMENT_TYPE_OPTIONS = [
    'Full-time', 'Part-time', 'Contract', 'Internship', 'Remote', 'Freelance',
]


class CandidateEducation(db.Model):
    __tablename__ = 'candidate_education'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    institution = db.Column(db.String(200), nullable=False)
    degree = db.Column(db.String(120), nullable=False)
    field_of_study = db.Column(db.String(120))
    is_current = db.Column(db.Boolean, default=False, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)


class CandidateExperience(db.Model):
    __tablename__ = 'candidate_experience'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    description = db.Column(db.Text)


class CandidateCertification(db.Model):
    __tablename__ = 'candidate_certifications'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    issuing_organization = db.Column(db.String(200), nullable=False)
    issue_year = db.Column(db.String(10))
    credential_id = db.Column(db.String(120))
    credential_url = db.Column(db.String(255))
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255))  # PDF, JPG, PNG
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def display_name(self):
        if not self.file_path:
            return ""
        name = self.file_path.split('/')[-1].split('\\')[-1]
        if '_' in name:
            parts = name.split('_', 1)
            if len(parts[0]) in (8, 32, 36) or parts[0].isalnum():
                return parts[1]
        return name

    @property
    def file_extension(self):
        if not self.file_path:
            return ""
        return self.file_path.rsplit('.', 1)[-1].lower() if '.' in self.file_path else ""


class Resume(db.Model):
    __tablename__ = 'resumes'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def display_name(self):
        if not self.file_path:
            return ""
        name = self.file_path.split('/')[-1].split('\\')[-1]
        if '_' in name:
            parts = name.split('_', 1)
            if len(parts[0]) in (8, 32, 36) or parts[0].isalnum():
                return parts[1]
        return name

    @property
    def file_extension(self):
        if not self.file_path:
            return ""
        return self.file_path.rsplit('.', 1)[-1].lower() if '.' in self.file_path else ""


# ---------------------------------------------------------------------------
# Company & Recruiter
# ---------------------------------------------------------------------------

class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    domain = db.Column(db.String(200), nullable=True)
    official_email = db.Column(db.String(120), nullable=True)
    ntn_id = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    industry = db.Column(db.String(100))
    website = db.Column(db.String(200))
    description = db.Column(db.Text)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_status = db.Column(db.String(30), default='Pending Verification', nullable=False)
    rejection_reason = db.Column(db.Text, nullable=True)
    organization_type = db.Column(db.String(50))
    company_size = db.Column(db.String(30))
    employment_types = db.Column(db.String(255))  # comma-separated
    working_since_months = db.Column(db.Integer, nullable=True)
    logo_path = db.Column(db.String(255), nullable=True)
    founded_date = db.Column(db.Date, nullable=True)
    onboarding_complete = db.Column(db.Boolean, default=False, nullable=False)

    def working_since_label(self):
        months = int(self.working_since_months or 0)
        if self.founded_date and months <= 0:
            from datetime import date
            today = date.today()
            months = (today.year - self.founded_date.year) * 12 + (today.month - self.founded_date.month)
            if today.day < self.founded_date.day:
                months -= 1
        years, rem = divmod(max(months, 0), 12)
        return f'Operating for {years} Years, {rem} Months'

    def calculate_completion_pct(self):
        checks = [
            bool(self.name and self.name.strip()),
            bool(self.industry and self.industry.strip()),
            bool(self.company_size and self.company_size.strip()),
            bool(self.location and self.location.strip()),
            bool(self.official_email and self.official_email.strip()),
            bool(self.domain and self.domain.strip()),
            bool(self.phone and self.phone.strip()),
            bool(self.ntn_id and self.ntn_id.strip()),
            bool(self.website and self.website.strip()),
            bool(self.description and self.description.strip()),
            bool(self.founded_date),
            bool(self.logo_path and self.logo_path.strip()),
        ]
        completed = sum(1 for c in checks if c)
        return int((completed / len(checks)) * 100)

    recruiters = db.relationship('Recruiter', backref='company', lazy='dynamic', cascade='all, delete-orphan')
    jobs = db.relationship('Job', backref='company', lazy='dynamic', cascade='all, delete-orphan')
    hiring_fields = db.relationship('CompanyHiringField', backref='company', lazy='dynamic', cascade='all, delete-orphan')
    offered_employment_types = db.relationship(
        'CompanyEmploymentType', backref='company', lazy='dynamic', cascade='all, delete-orphan',
    )


class CompanyHiringField(db.Model):
    """Job fields / categories this organization hires for — matches candidate interests."""
    __tablename__ = 'company_hiring_fields'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    field_name = db.Column(db.String(80), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('company_id', 'field_name', name='uq_company_field'),
        db.Index('ix_company_hiring_fields_company_id', 'company_id'),
    )


class CompanyEmploymentType(db.Model):
    __tablename__ = 'company_employment_types'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    employment_type = db.Column(db.String(40), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('company_id', 'employment_type', name='uq_company_employment_type'),
        db.Index('ix_company_employment_types_company_id', 'company_id'),
    )


class Recruiter(db.Model):
    __tablename__ = 'recruiters'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(120))
    title = db.Column(db.String(120))

    posted_jobs = db.relationship('Job', backref='posted_by_recruiter', lazy='dynamic', foreign_keys='Job.posted_by')
    shortlists = db.relationship('Shortlist', backref='shortlisted_by_recruiter', lazy='dynamic')


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class JobCategory(db.Model):
    __tablename__ = 'job_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    jobs = db.relationship('Job', backref='category', lazy='dynamic')


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('job_categories.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(120))
    salary_range = db.Column(db.String(80))
    salary_min = db.Column(db.Integer, nullable=True)
    salary_max = db.Column(db.Integer, nullable=True)
    employment_type = db.Column(db.String(50))  # Full-time, Part-time, Internship, Contract, Remote
    experience_required = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)
    approval_status = db.Column(db.String(20), default='approved', nullable=False)
    unpublish_reason = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    posted_by = db.Column(db.Integer, db.ForeignKey('recruiters.id'), nullable=False)
    logo_path = db.Column(db.String(255), nullable=True)
    is_hired = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    closes_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.Index('ix_jobs_status_approval_location', 'status', 'approval_status', 'location', 'category_id'),
    )

    skills = db.relationship('JobSkill', backref='job', lazy='dynamic', cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='job', lazy='dynamic', cascade='all, delete-orphan')
    saved_by = db.relationship('SavedJob', backref='job', lazy='dynamic', cascade='all, delete-orphan')
    shortlists = db.relationship('Shortlist', backref='job', lazy='dynamic', cascade='all, delete-orphan')
    complaints = db.relationship('Complaint', backref='job', lazy='dynamic', foreign_keys='Complaint.against_job_id')

    def is_open(self):
        if self.is_hired:
            return False
        closes = self.closes_at
        approved = (self.approval_status or 'approved') in ('approved', 'Approved')
        if not closes:
            return self.status == 'active' and approved
        return self.status == 'active' and approved and closes > datetime.utcnow()

    def accepts_applications(self):
        return self.is_open()


class JobSkill(db.Model):
    __tablename__ = 'job_skills'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    skill_name = db.Column(db.String(80), nullable=False)
    is_required = db.Column(db.Boolean, default=True, nullable=False)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

class Application(db.Model):
    __tablename__ = 'applications'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), nullable=True)
    cover_letter = db.Column(db.Text)
    screening_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='Applied', nullable=False)
    on_hold = db.Column(db.Boolean, default=False, nullable=False)
    hold_reason = db.Column(db.Text, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    withdrawn_at = db.Column(db.DateTime, nullable=True)
    is_read_by_employer = db.Column(db.Boolean, default=False, nullable=False)
    is_read_by_candidate = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('job_id', 'candidate_id', name='uq_job_candidate'),
        db.Index('ix_applications_job_candidate', 'job_id', 'candidate_id'),
    )

    resume = db.relationship('Resume', backref='applications')
    documents = db.relationship('ApplicationDocument', backref='application', lazy='dynamic', cascade='all, delete-orphan')
    status_history = db.relationship('ApplicationStatusHistory', backref='application', lazy='dynamic', cascade='all, delete-orphan')
    shortlist_entry = db.relationship('Shortlist', backref='application', uselist=False, cascade='all, delete-orphan')
    interviews = db.relationship('Interview', backref='application', lazy='dynamic', cascade='all, delete-orphan')
    offer = db.relationship('Offer', backref='application', uselist=False, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='application', lazy='dynamic')

    __table_args__ = (db.UniqueConstraint('job_id', 'candidate_id', name='uq_job_candidate'),)


class ApplicationDocument(db.Model):
    __tablename__ = 'application_documents'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    doc_type = db.Column(db.String(50))


class ApplicationStatusHistory(db.Model):
    __tablename__ = 'application_status_history'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    old_status = db.Column(db.String(30))
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    changed_by_user = db.relationship('User', backref='status_changes')


class Shortlist(db.Model):
    __tablename__ = 'shortlists'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False, unique=True)
    shortlisted_by = db.Column(db.Integer, db.ForeignKey('recruiters.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Interviews & Offers
# ---------------------------------------------------------------------------

class Interview(db.Model):
    __tablename__ = 'interviews'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    mode = db.Column(db.String(30), nullable=False)
    location_or_link = db.Column(db.String(255))
    status = db.Column(db.String(30), default='Scheduled', nullable=False)
    on_hold = db.Column(db.Boolean, default=False, nullable=False)
    hold_reason = db.Column(db.Text, nullable=True)
    reminder_sent = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    interviewers = db.relationship('Interviewer', backref='interview', lazy='dynamic', cascade='all, delete-orphan')


class Interviewer(db.Model):
    __tablename__ = 'interviewers'

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    feedback = db.Column(db.Text)
    rating = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref='interview_assignments')


class Offer(db.Model):
    __tablename__ = 'offers'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False, unique=True)
    salary_offered = db.Column(db.String(80))
    start_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='Pending', nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    responded_at = db.Column(db.DateTime)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

class SavedJob(db.Model):
    __tablename__ = 'saved_jobs'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint('candidate_id', 'job_id', name='uq_saved_job'),)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50))
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=True)
    body = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


class Complaint(db.Model):
    __tablename__ = 'complaints'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(50), unique=True, nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    raised_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    complainant_name = db.Column(db.String(120), nullable=True)
    complainant_email = db.Column(db.String(120), nullable=True)
    complainant_phone = db.Column(db.String(50), nullable=True)
    complainant_role = db.Column(db.String(50), nullable=True)
    reported_entity_type = db.Column(db.String(50), default='Job', nullable=False)
    reported_entity_id = db.Column(db.Integer, nullable=True)
    against_job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    subject = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=False)
    attachment_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(30), default='Pending', nullable=False)
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    raised_by_user = db.relationship('User', foreign_keys=[raised_by], backref='complaints_raised')
    complainant = db.relationship('User', foreign_keys=[user_id], backref='complaints')

    @property
    def sender_name(self):
        if self.complainant_name and self.complainant_name.strip():
            return self.complainant_name.strip()
        if self.complainant and self.complainant.name:
            return self.complainant.name
        if self.raised_by_user and self.raised_by_user.name:
            return self.raised_by_user.name
        return "Anonymous User"

    @property
    def sender_email(self):
        if self.complainant_email and self.complainant_email.strip():
            return self.complainant_email.strip()
        if self.complainant and self.complainant.email:
            return self.complainant.email
        if self.raised_by_user and self.raised_by_user.email:
            return self.raised_by_user.email
        return "Not Provided"

    @property
    def sender_role(self):
        if self.complainant_role and self.complainant_role.strip():
            return self.complainant_role.strip().title()
        if self.complainant and self.complainant.role:
            return self.complainant.role.title()
        if self.raised_by_user and self.raised_by_user.role:
            return self.raised_by_user.role.title()
        return "Guest Complainant"

    @property
    def target_job(self):
        from app.models import Job
        if self.against_job_id:
            j = Job.query.get(self.against_job_id)
            if j:
                return j
        if (self.reported_entity_type or '').lower() == 'job' and self.reported_entity_id:
            j = Job.query.get(self.reported_entity_id)
            if j:
                return j
        return None



class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Business logic helpers (testable independent of routes)
# ---------------------------------------------------------------------------

def create_audit_log(user_id, action, entity_type=None, entity_id=None, details=None):
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.session.add(log)
    return log


def log_status_change(application, new_status, changed_by_user_id):
    history = ApplicationStatusHistory(
        application_id=application.id,
        old_status=application.status,
        new_status=new_status,
        changed_by=changed_by_user_id,
    )
    application.status = new_status
    application.is_read_by_candidate = False
    if new_status != 'Rejected':
        application.rejection_reason = None
    db.session.add(history)
    return history


def can_apply(candidate_id, job):
    if not candidate_id:
        return False, 'Complete your candidate profile before applying.'
    if not job:
        return False, 'This job listing is unavailable.'
    try:
        open_ok = job.accepts_applications()
    except Exception:
        open_ok = getattr(job, 'status', None) == 'active'
    if not open_ok:
        return False, 'This job is no longer accepting applications.'
    existing = Application.query.filter_by(job_id=job.id, candidate_id=candidate_id).first()
    if existing and existing.status not in ['Withdrawn', 'Rejected']:
        return False, 'You have already applied for this job. You cannot re-apply unless your previous application is withdrawn or rejected by the employer.'

    active_apps_count = Application.query.filter(
        Application.candidate_id == candidate_id,
        Application.status.notin_(['Withdrawn', 'Rejected'])
    ).count()
    if active_apps_count >= 10:
        return False, 'Application limit reached! A single candidate can apply for a maximum of 10 jobs at the same time. Please wait for an employer response or withdraw an existing application.'

    return True, None


def can_post_job(company_id):
    if not company_id:
        return False, 'Company profile not found.'
    job_count = Job.query.filter_by(company_id=company_id).count()
    if job_count >= 20:
        return False, 'Job posting limit reached! A single employer can post up to 20 jobs on their dashboard.'
    return True, None


def setup_user_role(user, role, full_name=None):
    """Create candidate or employer profile after registration/onboarding."""
    name = full_name or user.name
    if role == 'candidate':
        if not user.candidate:
            db.session.add(Candidate(user_id=user.id, full_name=name, onboarding_complete=False))
    elif role == 'employer':
        if not user.recruiter:
            company = Company(name=f"{name}'s Company", onboarding_complete=False, verification_status='Pending Verification')
            db.session.add(company)
            db.session.flush()
            db.session.add(Recruiter(user_id=user.id, company_id=company.id, title='Recruiter'))
    if not user.role or user.role == 'pending':
        user.role = role
    if role in ('candidate', 'employer') and (not user.approval_status or user.approval_status == 'pending'):
        user.approval_status = 'approved'
        user.approval_note = None
        user.reviewed_at = None
        user.reviewed_by_id = None


def find_candidates_by_fields(field_names=None, search=''):
    """
    Return candidates whose interests or skills match the given field names.
    Used when employers filter talent by hiring category (e.g. Data Analysis).
    """
    from sqlalchemy import or_
    query = Candidate.query.filter(Candidate.onboarding_complete.is_(True))

    if search:
        query = query.filter(or_(
            Candidate.full_name.ilike(f'%{search}%'),
            Candidate.headline.ilike(f'%{search}%'),
            Candidate.location.ilike(f'%{search}%'),
        ))

    if not field_names:
        return query.order_by(Candidate.full_name).all()

    interest_ids = db.session.query(CandidateInterest.candidate_id).filter(
        CandidateInterest.interest_name.in_(field_names)
    )
    skill_ids = db.session.query(CandidateSkill.candidate_id).filter(
        CandidateSkill.skill_name.in_(field_names)
    )
    # Also match skills that contain the field name (e.g. skill "Python for Data Analysis")
    skill_like_clauses = [
        CandidateSkill.skill_name.ilike(f'%{f}%') for f in field_names
    ]
    skill_like_ids = db.session.query(CandidateSkill.candidate_id).filter(
        or_(*skill_like_clauses)
    ) if skill_like_clauses else []

    matched_ids = set(r[0] for r in interest_ids.all())
    matched_ids.update(r[0] for r in skill_ids.all())
    matched_ids.update(r[0] for r in skill_like_ids.all())

    if not matched_ids:
        return []

    return query.filter(Candidate.id.in_(matched_ids)).order_by(Candidate.full_name).all()


def candidate_matches_fields(candidate, field_names):
    """Check if a candidate matches any of the given field names."""
    if not field_names:
        return True
    interests = {i.interest_name for i in candidate.interests}
    skills = {s.skill_name for s in candidate.skills}
    for field in field_names:
        if field in interests:
            return True
        if field in skills:
            return True
        for skill in skills:
            if field.lower() in skill.lower():
                return True
    return False


class ContactMessage(db.Model):
    """Contact form submissions from the landing page."""
    __tablename__ = 'contact_messages'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def get_formatted_12hr_time():
    """
    Returns exact local device time in 12-hour format with AM/PM (e.g. '05:48:30 PM, 10 Sep 2026').
    """
    from datetime import datetime, timedelta, timezone
    pkt_tz = timezone(timedelta(hours=5))
    now = datetime.now(pkt_tz)
    return now.strftime("%I:%M:%S %p, %d %b %Y")


class AiChatMessage(db.Model):
    """
    Stores AI Resume Analyzer & Career Assistant Chat Messages in Supabase PostgreSQL.
    Includes exact 12-hour local device time (e.g. '05:48:30 PM, 10 Sep 2026').
    """
    __tablename__ = 'ai_chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=True)
    sender_role = db.Column(db.String(20), nullable=False, default='user')
    prompt_text = db.Column(db.Text, nullable=False)
    reply_text = db.Column(db.Text, nullable=True)
    match_score = db.Column(db.Integer, nullable=True)
    formatted_time = db.Column(db.String(60), nullable=False, default=get_formatted_12hr_time)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('ai_chat_messages', lazy='dynamic'))
    job = db.relationship('Job', backref=db.backref('ai_chat_messages', lazy='dynamic'))

