"""Safe button handling utilities to prevent errors in local testing mode."""

from flask import flash, redirect, url_for, session, current_app
from flask_login import current_user
from functools import wraps
import traceback


def safe_button_handler(default_redirect='auth.login'):
    """
    Decorator to safely handle button clicks and prevent AttributeError crashes.
    Provides mock data fallbacks when database relationships are missing.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except AttributeError as e:
                current_app.logger.error(f"AttributeError in button handler: {e}")
                current_app.logger.error(traceback.format_exc())
                
                # Check if we're in testing mode
                if current_app.config.get('TESTING_MODE'):
                    flash('Operation simulated in testing mode.', 'info')
                    # Return appropriate redirect based on user role
                    if current_user.is_authenticated:
                        if current_user.is_candidate():
                            return redirect(url_for('candidate.profile'))
                        elif current_user.is_employer():
                            return redirect(url_for('employer.dashboard'))
                        elif current_user.is_admin():
                            return redirect(url_for('admin.dashboard'))
                    return redirect(url_for(default_redirect))
                else:
                    flash('An error occurred. Please try again.', 'danger')
                    return redirect(url_for(default_redirect))
            except Exception as e:
                current_app.logger.error(f"Unexpected error in button handler: {e}")
                current_app.logger.error(traceback.format_exc())
                flash('An unexpected error occurred. Please try again.', 'danger')
                return redirect(url_for(default_redirect))
        return wrapped
    return decorator


def safe_get_candidate():
    """Safely get candidate object with mock fallback."""
    try:
        if current_user.is_authenticated and current_user.is_candidate():
            candidate = current_user.candidate
            if candidate is not None:
                return candidate
    except (AttributeError, Exception):
        pass
    
    # Fallback to mock data in testing mode
    if current_app.config.get('TESTING_MODE'):
        from app.mock_data import MockDataManager
        return MockDataManager.get_mock_candidate()
    
    return None


def safe_get_recruiter():
    """Safely get recruiter object with mock fallback."""
    try:
        if current_user.is_authenticated and current_user.is_employer():
            recruiter = current_user.recruiter
            if recruiter is not None:
                return recruiter
    except (AttributeError, Exception):
        pass
    
    # Fallback to mock data in testing mode
    if current_app.config.get('TESTING_MODE'):
        from app.mock_data import MockDataManager
        return {'company': MockDataManager.get_mock_company()}
    
    return None


def safe_get_company():
    """Safely get company object with mock fallback."""
    try:
        if current_user.is_authenticated and current_user.is_employer():
            recruiter = current_user.recruiter
            if recruiter and recruiter.company:
                return recruiter.company
    except (AttributeError, Exception):
        pass
    
    # Fallback to mock data in testing mode
    if current_app.config.get('TESTING_MODE'):
        from app.mock_data import MockDataManager
        return MockDataManager.get_mock_company()
    
    return None


def safe_flash_success(message, category='success'):
    """Safely flash a success message."""
    try:
        flash(message, category)
    except Exception:
        pass


def safe_flash_error(message, category='danger'):
    """Safely flash an error message."""
    try:
        flash(message, category)
    except Exception:
        pass


def safe_redirect(endpoint, **kwargs):
    """Safely redirect to an endpoint."""
    try:
        return redirect(url_for(endpoint, **kwargs))
    except Exception:
        return redirect(url_for('auth.login'))


def validate_form_submission(form):
    """Safely validate form with error handling."""
    try:
        if form and callable(getattr(form, 'validate_on_submit', None)):
            return form.validate_on_submit()
        return False
    except Exception:
        return False


def safe_form_data(form, field_name, default=''):
    """Safely get form data with fallback."""
    try:
        if form and hasattr(form, field_name):
            field = getattr(form, field_name)
            if hasattr(field, 'data'):
                return field.data or default
        return default
    except Exception:
        return default


def safe_request_form(field_name, default=''):
    """Safely get request form data with fallback."""
    try:
        from flask import request
        return request.form.get(field_name, default) or default
    except Exception:
        return default


def safe_file_upload(file_field, allowed_extensions, upload_folder):
    """Safely handle file upload with error handling."""
    try:
        if file_field and file_field.filename:
            from app.utils import save_upload
            return save_upload(file_field, upload_folder, allowed_extensions)
        return None
    except Exception as e:
        current_app.logger.error(f"File upload error: {e}")
        return None


def safe_execute_db_operation(operation, error_message='Database operation failed'):
    """Safely execute database operation with error handling."""
    try:
        from app.extensions import db
        result = operation()
        db.session.commit()
        return result
    except Exception as e:
        current_app.logger.error(f"{error_message}: {e}")
        from app.extensions import db
        db.session.rollback()
        return None


def mock_employer_pipeline_action(action_type, application_id):
    """
    Mock employer pipeline actions (Message, Wait, Reject) for testing mode.
    Returns success message without actual database operations.
    """
    messages = {
        'message': 'Message sent to candidate (Testing Mode).',
        'wait': 'Application kept Under Review (Testing Mode).',
        'reject': 'Application rejected (Testing Mode).'
    }
    
    return messages.get(action_type, 'Action completed (Testing Mode).')


def mock_candidate_action(action_type, item_id):
    """
    Mock candidate actions (Apply, Save Job, Update Profile) for testing mode.
    Returns success message without actual database operations.
    """
    messages = {
        'apply': 'Application submitted successfully (Testing Mode).',
        'save_job': 'Job saved to your list (Testing Mode).',
        'update_profile': 'Profile updated successfully (Testing Mode).',
        'delete_item': 'Item removed successfully (Testing Mode).',
    }
    
    return messages.get(action_type, 'Action completed (Testing Mode).')