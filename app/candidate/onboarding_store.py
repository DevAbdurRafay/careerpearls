"""Session-based candidate onboarding draft — used while TESTING_MODE is on."""

from flask import session
from flask_login import current_user

DRAFT_KEY = 'cp_onboarding_draft'
COMPLETE_KEY = 'cp_onboarding_complete'


def _draft_key():
    if current_user.is_authenticated:
        return f'{DRAFT_KEY}_{current_user.id}'
    return DRAFT_KEY


def _complete_key():
    if current_user.is_authenticated:
        return f'{COMPLETE_KEY}_{current_user.id}'
    return COMPLETE_KEY


def _default_draft():
    name = current_user.name if current_user.is_authenticated else ''
    return {
        'full_name': name,
        'phone': '',
        'location': '',
        'profile_image': '',
        'career_status': '',
        'interests': [],
        'headline': '',
        'availability': '',
        'work_mode': '',
        'bio': '',
        'has_internship': None,
        'internship_details': '',
        'education': [],
        'skills': [],
        'resumes': [],
    }


def get_draft():
    key = _draft_key()
    draft = session.get(key)
    if not draft:
        draft = _default_draft()
        session[key] = draft
    return draft


def update_draft(**fields):
    key = _draft_key()
    draft = get_draft()
    draft.update(fields)
    session[key] = draft
    session.modified = True
    return draft


def is_onboarding_complete():
    return bool(session.get(_complete_key()))


def mark_onboarding_complete():
    session[_complete_key()] = True
    session.modified = True


def clear_onboarding_session():
    if current_user.is_authenticated:
        session.pop(f'{DRAFT_KEY}_{current_user.id}', None)
        session.pop(f'{COMPLETE_KEY}_{current_user.id}', None)
    session.pop(DRAFT_KEY, None)
    session.pop(COMPLETE_KEY, None)
    session.pop('onboarding_max_step', None)


class SessionCandidateView:
    """Template-friendly view over session onboarding draft."""

    def __init__(self, draft=None):
        self._draft = draft or get_draft()

    @property
    def full_name(self):
        return self._draft.get('full_name') or (
            current_user.name if current_user.is_authenticated else ''
        )

    @property
    def phone(self):
        return self._draft.get('phone') or ''

    @property
    def location(self):
        return self._draft.get('location') or ''

    @property
    def profile_image(self):
        return self._draft.get('profile_image') or ''

    @property
    def career_status(self):
        return self._draft.get('career_status') or ''

    @property
    def headline(self):
        return self._draft.get('headline') or ''

    @property
    def availability(self):
        return self._draft.get('availability') or ''

    @property
    def work_mode(self):
        return self._draft.get('work_mode') or ''

    @property
    def bio(self):
        return self._draft.get('bio') or ''

    @property
    def has_internship(self):
        return self._draft.get('has_internship')

    @property
    def internship_details(self):
        return self._draft.get('internship_details') or ''

    @property
    def onboarding_complete(self):
        return is_onboarding_complete()

    @property
    def interests(self):
        class Interest:
            def __init__(self, name):
                self.interest_name = name

        return [Interest(n) for n in self._draft.get('interests', [])]

    @property
    def education(self):
        class Edu:
            def __init__(self, data, idx):
                self.id = idx
                self.institution = data.get('institution', '')
                self.degree = data.get('degree', '')
                self.field_of_study = data.get('field_of_study', '')
                self.is_current = data.get('is_current', False)
                self.start_date = None
                self.end_date = None

        return [Edu(e, i) for i, e in enumerate(self._draft.get('education', []))]

    @property
    def skills(self):
        class Skill:
            def __init__(self, data, idx):
                self.id = idx
                self.skill_name = data.get('skill_name', '')
                self.proficiency_level = data.get('proficiency_level', '')

        return [Skill(s, i) for i, s in enumerate(self._draft.get('skills', []))]

    @property
    def resumes(self):
        class ResumeItem:
            def __init__(self, data, idx):
                self.id = idx
                self.file_path = data.get('file_path', '')
                self.is_primary = data.get('is_primary', False)

        return [ResumeItem(r, i) for i, r in enumerate(self._draft.get('resumes', []))]

    @property
    def certifications(self):
        class CertItem:
            def __init__(self, data, idx):
                self.id = idx
                self.title = data.get('title', '')
                self.issuing_organization = data.get('issuing_organization', '')
                self.issue_year = data.get('issue_year', '')
                self.credential_id = data.get('credential_id', '')
                self.credential_url = data.get('credential_url', '')
                self.description = data.get('description', '')
                self.file_path = data.get('file_path', '')

        return [CertItem(c, i) for i, c in enumerate(self._draft.get('certifications', []))]

    def calculate_completion_pct(self):
        checks = [
            bool(self.full_name and self.full_name.strip()),
            bool(self.phone and self.phone.strip()),
            bool(self.location and self.location.strip()),
            bool(self.headline and self.headline.strip()),
            bool(self.availability and self.availability.strip()),
            bool(self.work_mode and self.work_mode.strip()),
            self.has_internship is not None,
            bool(self.profile_image and self.profile_image.strip()),
            len(self.education) > 0,
            len(self.skills) > 0,
        ]
        completed = sum(1 for c in checks if c)
        return int((completed / len(checks)) * 100)


def candidate_needs_onboarding():
    from flask import current_app

    if not current_user.is_authenticated or not current_user.is_candidate():
        return False
    if current_app.config.get('TESTING_MODE'):
        return not is_onboarding_complete()
    candidate = current_user.candidate
    return bool(candidate and not candidate.onboarding_complete)
