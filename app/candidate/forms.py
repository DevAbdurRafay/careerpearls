from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, FileField, SelectField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Optional, Length, Regexp
from app.models import WORK_MODE_OPTIONS, AVAILABILITY_OPTIONS, COUNTRY_CODES


class ProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(message='Full name is required.'), Length(max=120)])
    country_code = SelectField(
        'Country Code',
        choices=COUNTRY_CODES,
        default='+92',
        validators=[DataRequired(message='Country code is required.')],
    )
    phone = StringField('Phone', validators=[
        DataRequired(message='Phone number is required.'),
        Length(min=10, max=10, message='Phone number must be exactly 10 digits.'),
        Regexp(r'^\d{10}$', message='Phone number must contain exactly 10 digits (without country code).'),
    ])
    location = StringField('Location', validators=[DataRequired(message='Location is required.'), Length(max=120)])
    headline = StringField('Professional Headline', validators=[DataRequired(message='Headline is required.'), Length(max=200)])
    bio = TextAreaField('About Me', validators=[Optional(), Length(max=500, message='About me cannot exceed 500 characters.')])
    availability = SelectField(
        'Availability',
        choices=[('', 'Select availability')] + AVAILABILITY_OPTIONS,
        validators=[DataRequired(message='Please select availability.')],
    )
    work_mode = SelectField(
        'Work Preference',
        choices=[('', 'Select preference')] + WORK_MODE_OPTIONS,
        validators=[DataRequired(message='Please select work preference.')],
    )
    has_internship = SelectField(
        'Internship Experience',
        choices=[('', 'Select'), ('yes', 'Yes'), ('no', 'No')],
        validators=[DataRequired(message='Please select internship status.')],
    )
    internship_details = TextAreaField(
        'Internship Details',
        validators=[Optional(), Length(max=500, message='Internship details cannot exceed 500 characters.')],
    )
    linkedin_url = StringField('LinkedIn Profile', validators=[Optional(), Length(max=255)])
    github_url = StringField('GitHub Profile', validators=[Optional(), Length(max=255)])
    portfolio_url = StringField('Portfolio Website', validators=[Optional(), Length(max=255)])
    kaggle_url = StringField('Kaggle Profile', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Save Profile')


class OnboardingBasicForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(message='Full name is required.'), Length(min=2, max=120)])
    country_code = SelectField('Country Code', choices=COUNTRY_CODES, default='+92', validators=[DataRequired()])
    phone = StringField('Phone Number', validators=[
        DataRequired(message='Phone number is required.'),
        Length(min=10, max=10, message='Phone number must be 10 digits.'),
        Regexp(r'^\d{10}$', message='Enter 10 digits without country code.'),
    ])
    location = StringField('City / Location', validators=[DataRequired(message='Location is required.'), Length(max=120)])
    cropped_image = HiddenField('Cropped Image', validators=[Optional()])
    submit = SubmitField('Continue')


class OnboardingCareerForm(FlaskForm):
    career_status = StringField('Career Status', validators=[DataRequired(), Length(max=50)])
    submit = SubmitField('Continue')


class OnboardingProfessionalForm(FlaskForm):
    headline = StringField('Professional Headline', validators=[DataRequired(message='Headline is required.'), Length(max=200)])
    availability = SelectField('Availability', choices=[('', 'Select availability')] + AVAILABILITY_OPTIONS, validators=[DataRequired(message='Please select availability.')])
    work_mode = SelectField(
        'Work Preference',
        choices=[('', 'Select preference')] + WORK_MODE_OPTIONS,
        validators=[DataRequired(message='Please select work preference.')],
    )
    has_internship = SelectField(
        'Internship Experience',
        choices=[('', 'Select'), ('yes', 'Yes'), ('no', 'No')],
        validators=[DataRequired(message='Please select internship status.')],
    )
    internship_details = TextAreaField('Internship Details', validators=[Optional(), Length(max=500)])
    bio = TextAreaField('About You', validators=[Optional(), Length(max=500, message='Cannot exceed 500 characters.')])
    submit = SubmitField('Continue')


class OnboardingCredentialsForm(FlaskForm):
    institution = StringField('Institution', validators=[Optional(), Length(max=200)])
    degree = StringField('Degree / Program', validators=[Optional(), Length(max=120)])
    skill_name = StringField('Skill', validators=[Optional(), Length(max=80)])
    proficiency_level = SelectField('Level', choices=[
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Advanced', 'Advanced'),
        ('Expert', 'Expert'),
    ], validators=[Optional()])
    cropped_image = HiddenField('Cropped Image', validators=[Optional()])
    submit = SubmitField('Complete Setup')


class PhotoUploadForm(FlaskForm):
    photo = FileField('Profile Photo', validators=[Optional()])
    cropped_image = HiddenField('Cropped Image', validators=[Optional()])
    submit = SubmitField('Save Photo')


class ResumeUploadForm(FlaskForm):
    resume = FileField('Upload Resume (PDF, JPEG, PNG — max 15MB)', validators=[DataRequired()])
    submit = SubmitField('Upload')


class EducationForm(FlaskForm):
    institution = StringField('Institution', validators=[DataRequired(), Length(max=200)])
    degree = StringField('Degree / Program', validators=[DataRequired(), Length(max=120)])
    field_of_study = StringField('Field of Study', validators=[Optional(), Length(max=120)])
    is_current = BooleanField('Currently studying here')
    start_year = StringField('Start Year', validators=[Optional(), Length(max=4)])
    end_year = StringField('End Year (or expected)', validators=[Optional(), Length(max=4)])
    submit = SubmitField('Add Education')


class SkillForm(FlaskForm):
    skill_name = StringField('Skill', validators=[DataRequired(), Length(max=80)])
    proficiency_level = SelectField('Level', choices=[
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Advanced', 'Advanced'),
        ('Expert', 'Expert'),
    ])
    submit = SubmitField('Add Skill')


class CertificationForm(FlaskForm):
    title = StringField('Certification Title', validators=[DataRequired(message='Title is required.'), Length(max=200)])
    issuing_organization = StringField('Issuing Organization', validators=[DataRequired(message='Issuing organization is required.'), Length(max=200)])
    issue_year = StringField('Issue Year', validators=[Optional(), Length(max=10)])
    credential_id = StringField('Credential ID', validators=[Optional(), Length(max=120)])
    credential_url = StringField('Credential URL', validators=[Optional(), Length(max=255)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    certificate_file = FileField('Upload Certificate (PDF, JPEG, PNG — max 25MB)', validators=[DataRequired(message='Please upload a certificate document file.')])
    submit = SubmitField('Add Certification')


class SocialLinksForm(FlaskForm):
    github_url = StringField('GitHub Profile', validators=[Optional(), Length(max=255)])
    linkedin_url = StringField('LinkedIn Profile', validators=[Optional(), Length(max=255)])
    kaggle_url = StringField('Kaggle Profile', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Save Links')

