from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from backend.aiagent.multi_agent_analysis import analyze_with_agents
from scripts.sliding_window import correlate_logs
from internal.routes import api_logs
from config.config import (
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_MODEL,
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME
)
import uuid
import openai

# Azure OpenAI Setup
openai.api_key = AZURE_OPENAI_KEY
openai.api_base = AZURE_OPENAI_ENDPOINT
openai.api_type = "azure"
openai.api_version = "2024-02-01"

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3005"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    trace_id: str

class AnalyzeRequest(BaseModel):
    logs: List[LogEntry]

# Analyze logs route
@app.post("/analyze")
async def analyze_logs(request: AnalyzeRequest):
    logs_by_trace = {}
    for log in request.logs:
        logs_by_trace.setdefault(log.trace_id, []).append(log.dict())

    formatted_windows = []
    for trace_id, logs in logs_by_trace.items():
        log_chunk = "\n".join(f"[{log['timestamp']}] {log['level']}: {log['message']}" for log in logs)
        formatted_windows.append(log_chunk)

    results = analyze_with_agents(formatted_windows)
    return {"results": results}

# Include other API routes
app.include_router(api_logs.router)
