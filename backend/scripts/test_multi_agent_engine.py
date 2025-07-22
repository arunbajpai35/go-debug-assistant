# scripts/test_multi_agent_engine.py

import os
import json
from dotenv import load_dotenv
from aiagent.multi_agent_analysis import analyze_with_agents

# Load your Together API key from .env
load_dotenv()

if not os.getenv("TOGETHER_API_KEY"):
    raise EnvironmentError("❌ TOGETHER_API_KEY not found. Please create a .env file in the root directory with your API key.")

# Sample log window for testing
log_window = """
2025-07-20T13:00:00Z ERROR: Timeout when connecting to db
2025-07-20T13:00:01Z INFO: Retrying request...
2025-07-20T13:00:02Z ERROR: Token expired
2025-07-20T13:00:30Z INFO: Forwarded request to payment-service
2025-07-20T13:00:59Z INFO: Request completed
2025-07-20T13:01:00Z INFO: Generated token for user 123
2025-07-20T13:01:02Z ERROR: Token verification failed
2025-07-20T13:01:20Z INFO: Fetched profile data
2025-07-20T13:01:25Z INFO: Retrying login...
2025-07-20T13:01:59Z INFO: Login succeeded
"""

if __name__ == "__main__":
    print("🚀 Running multi-agent analysis on test logs...\n")

    # Run the analyzer with the sample window (list of 1 window)
    results = analyze_with_agents([log_window])

    print("\n📊 Final Multi-Agent Output:")
    print(json.dumps(results, indent=2))
