import os, re

base_dir = r"c:\Users\HP\Desktop\CareerPearls\app"

for root, dirs, files in os.walk(base_dir):
    for file in files:
        if file.endswith('.py'):
            fp = os.path.join(root, file)
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            if 'send_email' in content or 'Mail' in content or 'Message(' in content:
                print(f"Found in {fp}")
