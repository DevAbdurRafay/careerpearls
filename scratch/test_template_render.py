import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")

from app import create_app, db
from app.models import User, Candidate, Application, Job
from flask import render_template

app = create_app()

with app.app_context():
    cand = Candidate.query.first()
    if cand:
        user = cand.user
        with app.test_request_context('/candidate/dashboard'):
            try:
                # Test render candidate/dashboard.html
                apps_by_status = {'Applied': []}
                hired_apps = []
                html = render_template('candidate/dashboard.html', 
                                       candidate=cand, 
                                       applications=[], 
                                       apps_by_status=apps_by_status, 
                                       hired_apps=hired_apps,
                                       is_hired=False,
                                       unread_count=0)
                print("SUCCESS: candidate/dashboard.html rendered cleanly without TemplateSyntaxError!")
            except Exception as e:
                import traceback
                print("ERROR rendering candidate/dashboard.html:", type(e), e)
                traceback.print_exc()
    else:
        print("No candidate found in DB to test.")
