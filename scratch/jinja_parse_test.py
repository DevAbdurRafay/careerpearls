import sys, os
from jinja2 import Environment, FileSystemLoader

template_dir = r"c:\Users\HP\Desktop\CareerPearls\app\candidate\templates\candidate"
loader = FileSystemLoader([
    template_dir,
    r"c:\Users\HP\Desktop\CareerPearls\app\templates"
])

env = Environment(loader=loader)
try:
    tpl = env.get_template('dashboard.html')
    print("SUCCESS: dashboard.html parsed successfully by Jinja2 environment without any TemplateSyntaxError!")
except Exception as e:
    import traceback
    print("TemplateSyntaxError found:", type(e), e)
    traceback.print_exc()
