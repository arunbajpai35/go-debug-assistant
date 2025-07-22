import requests
import json

log = {
    "timestamp": "2025-07-20T13:00:00Z",
    "service": "payment-service",
    "level": "ERROR",
    "message": "Timeout while connecting to database"
}

response = requests.post("http://localhost:8080/logs", json=log)
print("Status:", response.status_code)
