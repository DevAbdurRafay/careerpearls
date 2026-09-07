import os, re

base_dir = r"c:\Users\HP\Desktop\CareerPearls\app"

route_files = [
    os.path.join(base_dir, "candidate", "routes.py"),
    os.path.join(base_dir, "employer", "routes.py"),
    os.path.join(base_dir, "admin", "routes.py"),
    os.path.join(base_dir, "jobboard", "routes.py"),
    os.path.join(base_dir, "api", "routes.py"),
]

print("=== Checking queries for order_by across routes ===")
for rpath in route_files:
    if not os.path.exists(rpath):
        continue
    with open(rpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f"\n--- File: {os.path.basename(rpath)} ---")
    for idx, l in enumerate(lines):
        if '.query' in l or '.order_by' in l:
            if 'all()' in l or 'first()' in l or 'paginate(' in l or 'order_by' in l:
                print(f"Line {idx+1}: {l.strip()[:140]}")
