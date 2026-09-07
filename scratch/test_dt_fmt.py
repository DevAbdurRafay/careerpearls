from datetime import datetime, timedelta, timezone

def test_fmt(dt_val):
    if not dt_val:
        return ""
    if isinstance(dt_val, str):
        from dateutil import parser
        dt_val = parser.parse(dt_val)
    
    local_tz = timezone(timedelta(hours=5))
    if hasattr(dt_val, 'tzinfo') and dt_val.tzinfo is not None:
        dt_local = dt_val.astimezone(local_tz)
    else:
        dt_local = dt_val + timedelta(hours=5)
    return dt_local.strftime('%Y-%m-%d %I:%M:%S %p')

now_utc = datetime.utcnow()
print("UTC Now:", now_utc)
print("Local Formatted 12h:", test_fmt(now_utc))
