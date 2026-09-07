import re
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField, DateTimeField, EmailField
from wtforms.validators import DataRequired, Optional, Length, URL, ValidationError, Email


def optional_url(form, field):
    if field.data:
        from wtforms.validators import URL
        URL()(form, field)


def no_numbers_validator(form, field):
    if field.data and re.search(r'\d', field.data):
        raise ValidationError(f"{field.label.text} cannot contain numbers. Please use letters and standard punctuation only.")


def max_500_chars(form, field):
    if field.data and len(field.data.strip()) > 500:
        raise ValidationError(f"{field.label.text} cannot exceed 500 characters. (Current length: {len(field.data.strip())})")


class CompanyProfileForm(FlaskForm):
    name = StringField('Company Name *', validators=[DataRequired(message='Company name is required.'), Length(max=200)])
    recruiter_name = StringField('Recruiter Name', validators=[Optional(), Length(max=120)])
    title = StringField('Title / Position', validators=[Optional(), Length(max=120)])
    domain = StringField('Domain', validators=[Optional(), Length(max=200)])
    official_email = EmailField('Official Email', validators=[Optional(), Email(message='Please enter a valid email address.')])
    ntn_id = StringField('NTN ID', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    location = StringField('Location', validators=[Optional(), Length(max=120)])
    industry = StringField('Industry', validators=[Optional(), Length(max=100)])
    company_size = SelectField('Company Size', choices=[
        ('', 'Select company size'),
        ('1-10', '1–10 employees'),
        ('11-50', '11–50 employees'),
        ('51-200', '51–200 employees'),
        ('201-500', '201–500 employees'),
        ('500+', '500+ employees'),
    ], validators=[Optional()])
    website = StringField('Website', validators=[Optional(), Length(max=200), optional_url])
    description = TextAreaField('Description', validators=[Optional(), max_500_chars])
    submit = SubmitField('Save Company Profile')


class JobPostForm(FlaskForm):
    title = StringField('Job Title *', validators=[
        DataRequired(message='Job title is required.'),
        Length(min=3, max=100, message='Job title must be between 3 and 100 characters.'),
        no_numbers_validator
    ])
    category_id = SelectField('Job Category *', coerce=int, validators=[DataRequired(message='Please select a job category.')])
    employment_type = SelectField('Employment Type *', choices=[
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Contract', 'Contract'),
        ('Internship', 'Internship'),
        ('Remote', 'Remote'),
        ('Hybrid', 'Hybrid'),
    ], validators=[DataRequired(message='Employment type is required.')])
    experience_required = SelectField('Experience Required *', choices=[
        ('Fresh / Entry Level (0-1 Year)', 'Fresh / Entry Level (0-1 Year)'),
        ('Junior Level (1-3 Years)', 'Junior Level (1-3 Years)'),
        ('Mid-Level (3-5 Years)', 'Mid-Level (3-5 Years)'),
        ('Senior Level (5-8 Years)', 'Senior Level (5-8 Years)'),
        ('Lead / Principal (8+ Years)', 'Lead / Principal (8+ Years)'),
        ('Executive / Director (10+ Years)', 'Executive / Director (10+ Years)'),
        ('Based on Experience', 'Based on Experience'),
    ], validators=[DataRequired(message='Please specify experience level.')])
    location = StringField('Job Location (City / Remote) *', validators=[
        DataRequired(message='Job location is required.'),
        Length(max=100, message='Location must be under 100 characters.'),
        no_numbers_validator
    ])
    salary_range = StringField('Salary Range *', validators=[
        DataRequired(message='Please select or enter a salary range.'),
        Length(max=100)
    ])
    closes_at = DateTimeField('Application Deadline *', format='%Y-%m-%dT%H:%M', validators=[
        DataRequired(message='Closing deadline date & time is required.')
    ])
    description = TextAreaField('Job Description * (Max 1500 characters)', validators=[
        DataRequired(message='Job description is required.'),
        Length(min=20, max=1500, message='Description must be between 20 and 1500 characters.')
    ])
    skills = StringField('Required Skills * (comma-separated)', validators=[
        DataRequired(message='Please provide at least one required skill.'),
        Length(max=250)
    ])
    submit = SubmitField('Publish Job Listing')


class ApplicationStatusForm(FlaskForm):
    status = SelectField('Status', choices=[
        ('Under Review', 'Under Review'),
        ('Contacted', 'Contacted'),
        ('Rejected', 'Rejected'),
    ], validators=[DataRequired()])
    submit = SubmitField('Update Status')


class InterviewScheduleForm(FlaskForm):
    scheduled_at = DateTimeField('Date & Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    mode = SelectField('Mode', choices=[
        ('Video', 'Video'),
        ('In-person', 'In-person'),
        ('Phone', 'Phone'),
    ], validators=[DataRequired()])
    location_or_link = StringField('Location or Link', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Schedule Interview')
