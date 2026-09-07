from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp
from app.models import User
from app.auth.validators import validate_password_strength


class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Sign In')


class RegisterForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters.'),
        validate_password_strength,
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords do not match.'),
    ])
    submit = SubmitField('Create Account')

    def validate_email(self, field):
        existing = User.query.filter_by(email=field.data.lower()).first()
        if existing:
            role_name = existing.role.title() if existing.role else 'User'
            raise ValidationError(
                f'An account with this email already exists as a {role_name}. Please log in or deactivate your existing account first.'
            )


class VerifyCodeForm(FlaskForm):
    code = StringField(
        'Verification Code',
        validators=[
            DataRequired(message='Please enter the 6-digit code.'),
            Length(min=6, max=6, message='Code must be exactly 6 digits.'),
            Regexp(r'^\d{6}$', message='Code must contain only numbers.'),
        ],
    )
    submit = SubmitField('Verify & Create Account')


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Verification Code')


class VerifyResetCodeForm(FlaskForm):
    code = StringField(
        'Verification Code',
        validators=[
            DataRequired(message='Please enter the 6-digit code.'),
            Length(min=6, max=6, message='Code must be exactly 6 digits.'),
            Regexp(r'^\d{6}$', message='Code must contain only numbers.'),
        ],
    )
    submit = SubmitField('Verify Code')



class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters.'),
        validate_password_strength,
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords do not match.'),
    ])
    submit = SubmitField('Reset Password')


class OAuthOnboardingForm(FlaskForm):
    role = SelectField('I am joining as', choices=[
        ('candidate', 'Candidate — looking for jobs'),
        ('employer', 'Employer — hiring talent'),
    ], validators=[DataRequired()])
    submit = SubmitField('Continue')
