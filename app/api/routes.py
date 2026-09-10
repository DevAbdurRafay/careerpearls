from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import Job, Application, JobCategory, Company, User, Candidate
from app.utils import role_required, get_recruiter_or_403

api_bp = Blueprint('api', __name__)


@api_bp.route('/jobs')
def api_jobs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('q', '')

    query = Job.query.filter(
        Job.status == 'active',
        or_(Job.is_hired == False, Job.is_hired.is_(None)),
        Job.closes_at > datetime.utcnow()
    )
    if search:
        query = query.filter(Job.title.ilike(f'%{search}%'))

    pagination = query.order_by(Job.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'jobs': [{
            'id': j.id,
            'title': j.title,
            'company': j.company.name,
            'location': j.location,
            'employment_type': j.employment_type,
            'salary_range': j.salary_range,
            'created_at': j.created_at.isoformat(),
            'closes_at': j.closes_at.isoformat(),
        } for j in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page,
    })


@api_bp.route('/jobs/<int:job_id>')
def api_job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    return jsonify({
        'id': job.id,
        'title': job.title,
        'description': job.description,
        'company': job.company.name,
        'location': job.location,
        'employment_type': job.employment_type,
        'salary_range': job.salary_range,
        'category': job.category.name,
        'skills': [{'name': s.skill_name, 'required': s.is_required} for s in job.skills],
        'status': job.status,
        'is_open': job.accepts_applications(),
    })


@api_bp.route('/applications')
@login_required
@role_required('candidate')
def api_my_applications():
    candidate = current_user.candidate
    apps = Application.query.filter_by(candidate_id=candidate.id).order_by(
        Application.applied_at.desc()
    ).all()
    return jsonify({
        'applications': [{
            'id': a.id,
            'job_title': a.job.title,
            'company': a.job.company.name,
            'status': a.status,
            'applied_at': a.applied_at.isoformat(),
        } for a in apps]
    })


@api_bp.route('/categories')
def api_categories():
    categories = JobCategory.query.order_by(JobCategory.name).all()
    return jsonify({'categories': [{'id': c.id, 'name': c.name} for c in categories]})


@api_bp.route('/employer/verification-status')
@login_required
@role_required('employer')
def api_employer_verification_status():
    """API endpoint to check employer verification status in real-time"""
    try:
        recruiter = get_recruiter_or_403()
        company = recruiter.company
        if company:
            return jsonify({
                'status': company.verification_status,
                'is_verified': company.is_verified,
                'rejection_reason': company.rejection_reason
            })
        return jsonify({'status': 'Unknown', 'is_verified': False, 'rejection_reason': None})
    except Exception as e:
        return jsonify({'status': 'Error', 'is_verified': False, 'rejection_reason': None}), 500


@api_bp.route('/admin/dashboard-data')
def api_admin_dashboard_data():
    """API endpoint to provide real-time dashboard data for admin panel"""
    try:
        from app.utils import get_current_admin
        admin = get_current_admin()
        if not admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Get latest employer data
        recent_employer = User.query.filter_by(role='employer').order_by(User.created_at.desc()).first()
        
        employer_data = None
        if recent_employer and recent_employer.recruiter and recent_employer.recruiter.company:
            company = recent_employer.recruiter.company
            employer_data = {
                'id': recent_employer.id,
                'name': recent_employer.name,
                'email': recent_employer.email,
                'company': {
                    'name': company.name,
                    'company_size': company.company_size,
                    'logo_path': company.logo_path,
                    'verification_status': company.verification_status,
                    'is_verified': company.is_verified,
                    'rejection_reason': company.rejection_reason
                },
                'created_at': recent_employer.created_at.isoformat() if recent_employer.created_at else None
            }
        
        # Get current statistics
        total_users = User.query.count()
        candidates = Candidate.query.count()
        employers = User.query.filter_by(role='employer').count()
        active_jobs = Job.query.filter_by(status='active').count()
        
        from app.models import Complaint
        pending_complaints = Complaint.query.filter(
            Complaint.status.in_(['Open', 'In Review'])
        ).count()
        
        pending_employers = Company.query.filter_by(verification_status='Pending Verification').count()
        verified_employers = Company.query.filter_by(verification_status='Approved').count()
        rejected_employers = Company.query.filter_by(verification_status='Rejected').count()
        
        return jsonify({
            'recent_employer': employer_data,
            'stats': {
                'total_users': total_users,
                'candidates': candidates,
                'employers': employers,
                'active_jobs': active_jobs,
                'pending_complaints': pending_complaints,
                'pending_employers': pending_employers,
                'verified_employers': verified_employers,
                'rejected_employers': rejected_employers
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
