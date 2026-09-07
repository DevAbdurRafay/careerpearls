import os, re

base_dir = r"c:\Users\HP\Desktop\CareerPearls"

def check_status_updates():
    for root, dirs, files in os.walk(base_dir):
        if 'venv' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                if '.status =' in content or '.status=' in content:
                    lines = content.splitlines()
                    for idx, l in enumerate(lines):
                        if '.status =' in l or '.status=' in l:
                            print(f"{filepath}:{idx+1} - {l.strip()}")

check_status_updates()
