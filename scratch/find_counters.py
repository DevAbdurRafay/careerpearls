import os, re

base_dir = r"c:\Users\HP\Desktop\CareerPearls"

def find_in_files(pattern):
    results = []
    for root, dirs, files in os.walk(base_dir):
        if 'venv' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith(('.py', '.html')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            results.append(f"{filepath}:{idx+1} - {line.strip()}")
                except Exception:
                    pass
    return results

print("=== Search for applications counter / badge ===")
for r in find_in_files(r'My Applications|application_count|unread|is_read_by'):
    print(r[:150])
