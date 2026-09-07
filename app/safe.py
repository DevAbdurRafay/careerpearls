"""Safe utility functions for attribute access and profile validation."""


def gattr(obj, attr, default=None):
    """
    Safely get an attribute from an object, returning default if the object is None or attribute doesn't exist.
    This replaces hasattr/getattr usage in templates which caused Jinja2 errors.
    """
    if obj is None:
        return default
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def ensure_recruiter_profile(user):
    """
    Ensure a recruiter profile exists for the given user.
    Returns the recruiter object if it exists, None otherwise.
    """
    if not user or not user.is_authenticated:
        return None
    
    try:
        return user.recruiter
    except AttributeError:
        return None
