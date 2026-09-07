import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")

from jinja2 import Environment, FileSystemLoader

print("=== Testing Jinja2 Template Parsing ===")
template_dirs = [
    r"c:\Users\HP\Desktop\CareerPearls\app\candidate\templates\candidate",
    r"c:\Users\HP\Desktop\CareerPearls\app\templates"
]
env = Environment(loader=FileSystemLoader(template_dirs))

templates_to_test = ['dashboard.html', 'explore.html', 'landing.html']
for tname in templates_to_test:
    try:
        t = env.get_template(tname)
        print(f"SUCCESS: {tname} parsed cleanly without syntax errors!")
    except Exception as e:
        print(f"ERROR in {tname}: {e}")

print("\n=== Testing Python Imports & Email Helper Functions ===")
try:
    from app.email_utils import (
        send_job_application_email,
        send_job_withdrawal_email,
        send_job_notifier_email
    )
    print("SUCCESS: Email helper functions imported cleanly!")
except Exception as e:
    print(f"ERROR importing email helpers: {e}")
