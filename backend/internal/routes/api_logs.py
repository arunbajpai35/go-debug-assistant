# internal/routes/api_logs.py
from fastapi import APIRouter
import redis
import json

router = APIRouter()
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

@router.get("/logs/{trace_id}")
def get_analysis(trace_id: str):
    key = f"analysis:{trace_id}"
    data = r.get(key)
    if data:
        return json.loads(data)
    return {"error": "Trace not found"}
