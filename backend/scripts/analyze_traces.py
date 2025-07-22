import requests
import json
from collections import defaultdict
from datetime import datetime, timedelta

# Dummy logs – in real case, load from DB, log file, or ingestion system
logs = [
    {
        "timestamp": "2025-07-21T13:45:00",
        "level": "ERROR",
        "message": "Timeout while connecting to database",
        "trace_id": "trace-123"
    },
    {
        "timestamp": "2025-07-21T13:45:05",
        "level": "WARN",
        "message": "Retrying database connection",
        "trace_id": "trace-123"
    },
    {
        "timestamp": "2025-07-21T14:10:00",
        "level": "ERROR",
        "message": "Payment gateway returned 500",
        "trace_id": "trace-456"
    }
]

# === STEP 1: Group logs by trace_id ===
def group_by_trace_id(logs):
    trace_map = defaultdict(list)
    for log in logs:
        trace_map[log["trace_id"]].append(log)
    return trace_map

# === STEP 2: Call /analyze endpoint ===
def call_analyze_api(trace_id, logs, model="gpt-4o-mini"):
    payload = {
        "logs": logs,
        "model": model
    }

    try:
        res = requests.post("http://127.0.0.1:8000/analyze", json=payload)
        print(f"\n🧠 Analysis for Trace ID: {trace_id}")
        print("Status:", res.status_code)
        print("Response:", res.json())
    except Exception as e:
        print(f"❌ Error analyzing trace {trace_id}: {e}")

# === MAIN ===
if __name__ == "__main__":
    grouped = group_by_trace_id(logs)

    for trace_id, log_group in grouped.items():
        call_analyze_api(trace_id, log_group)
