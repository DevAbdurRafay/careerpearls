with open(r"c:\Users\HP\Desktop\CareerPearls\app\models\__init__.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "class Candidate" in line:
        print(f"Line {idx+1}: {line.strip()}")
