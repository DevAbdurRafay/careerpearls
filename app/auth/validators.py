import re

from wtforms.validators import ValidationError

PASSWORD_GUIDELINES = (
    'Password must include at least one uppercase letter, one lowercase letter, '
    'one number, and one special character.'
)


def validate_password_strength(form, field):
    value = field.data or ''
    missing = []

    if not re.search(r'[A-Z]', value):
        missing.append('uppercase letter')
    if not re.search(r'[a-z]', value):
        missing.append('lowercase letter')
    if not re.search(r'\d', value):
        missing.append('number')
    if not re.search(r'[^\w\s]', value):
        missing.append('special character')

    if missing:
        raise ValidationError(
            f'Password must include: {", ".join(missing)}. '
            'Use uppercase, lowercase, a number, and a special character.'
        )
