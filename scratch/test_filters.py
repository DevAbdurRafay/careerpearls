import sys, os
sys.path.insert(0, r"c:\Users\HP\Desktop\CareerPearls")

from app import create_app
from datetime import datetime

app = create_app()

with app.app_context():
    filter_func = app.jinja_env.filters['format_dt12']
    dt12_func = app.jinja_env.filters['dt12']
    dt12_short_func = app.jinja_env.filters['dt12_short']
    
    test_dates = [
        datetime(2026, 9, 1, 14, 30, 0), # Old saved UTC timestamp
        datetime(2026, 9, 7, 6, 45, 0),  # Recent UTC timestamp
        "2026-09-07T06:50:00Z"           # ISO String
    ]
    
    print("=== Jinja Datetime Filter Test ===")
    for d in test_dates:
        print("Input:", d)
        print("  -> format_dt12 :", filter_func(d))
        print("  -> dt12        :", dt12_func(d))
        print("  -> dt12_short  :", dt12_short_func(d))
