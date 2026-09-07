with open(r"c:\Users\HP\Desktop\CareerPearls\app\employer\routes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "is_read_by_employer" in line or "manage_applications" in line or "def dashboard" in line:
        print(f"Line {idx+1}: {line.strip()}")
