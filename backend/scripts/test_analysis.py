import requests
from analyze_log import analyze_log

# Local log analysis
log_msg = "payment-service ERROR Timeout while connecting to database"
local_result = analyze_log(log_msg)
print("🔍 Local AI Analysis:")
print(local_result)

# API log analysis
api_payload = {
    "logs": [
        {
            "timestamp": "2025-07-21T13:45:00",
            "level": "ERROR",
            "message": "Timeout while connecting to database",
            "trace_id": "trace-123"
        }
    ],
    "model": "gpt-4o-mini"
}

response = requests.post("http://localhost:8000/analyze", json=api_payload)

print("\n🌐 API AI Analysis:")
print("Status:", response.status_code)
print("Response:", response.json())
