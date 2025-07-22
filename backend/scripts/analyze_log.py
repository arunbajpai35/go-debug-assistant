import os
import requests
import configparser
import psycopg2
import redis
import json

# Load config
config = configparser.ConfigParser()
config.read("config/config.ini")

# Azure OpenAI credentials
AZURE_API_KEY = config.get("azure_openai", "api_key", fallback=None)
AZURE_ENDPOINT = config.get("azure_openai", "endpoint", fallback=None)
AZURE_DEPLOYMENT = config.get("azure_openai", "deployment_name", fallback=None)
AZURE_API_VERSION = config.get("azure_openai", "api_version", fallback="2024-02-01")

# Together API key
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# Redis setup (optional)
redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

# PostgreSQL setup
def save_to_postgres(trace_id, service, log, ai_summary, root_cause, suggestion):
    try:
        conn = psycopg2.connect(
            host=config.get("database", "host", fallback="localhost"),
            port=config.getint("database", "port"),
            dbname=config.get("database", "dbname"),
            user=config.get("database", "user"),
            password=config.get("database", "password")
        )
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO analysis_results (trace_id, service, log, ai_summary, root_cause, suggestion)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (trace_id, service, log, ai_summary, root_cause, suggestion))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB Save Error] {e}")

# Optional Redis cache
def cache_to_redis(trace_id, result_dict):
    redis_client.set(f"analysis:{trace_id}", json.dumps(result_dict), ex=3600)

# Main log analyzer
def analyze_log(log_message, model="gpt-4o-mini", trace_id="trace-1234", service="unknown-service"):
    prompt = f"""You're a backend debugging assistant.
A log message was received: {log_message}
Provide:
1. A concise root-cause hypothesis.
2. Steps to debug or fix."""

    try:
        if model == "gpt-4o-mini":
            if not (AZURE_API_KEY and AZURE_ENDPOINT and AZURE_DEPLOYMENT):
                return "[GPT-4o-mini Error: Missing Azure config]"

            url = f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_DEPLOYMENT}/chat/completions?api-version={AZURE_API_VERSION}"
            headers = {
                "Content-Type": "application/json",
                "api-key": AZURE_API_KEY
            }
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            }
            resp = requests.post(url, headers=headers, json=payload)
            data = resp.json()
            ai_response = data["choices"][0]["message"]["content"]
            print("Azure API response:", ai_response)

        elif model == "deepseek":
            if not TOGETHER_API_KEY:
                return "[DeepSeek Error: TOGETHER_API_KEY not set]"
            resp = requests.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={"Authorization": f"Bearer {TOGETHER_API_KEY}"},
                json={
                    "model": "deepseek-ai/DeepSeek-R1-0528",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
            )
            data = resp.json()
            ai_response = data["choices"][0]["message"]["content"]
            print("Together API response:", ai_response)

        else:
            return f"[Error: Unsupported model '{model}']"

        # Parse the response into sections (assumes format like "1. Root cause\n2. Fix")
        root_cause = "Unknown"
        suggestion = "Unknown"

        if "1." in ai_response and "2." in ai_response:
            parts = ai_response.split("2.")
            root_cause = parts[0].replace("1.", "").strip()
            suggestion = parts[1].strip()

        # Save to PostgreSQL
        save_to_postgres(
            trace_id=trace_id,
            service=service,
            log=log_message,
            ai_summary=ai_response,
            root_cause=root_cause,
            suggestion=suggestion
        )

        # Optional: cache to Redis
        cache_to_redis(trace_id, {
            "trace_id": trace_id,
            "service": service,
            "log": log_message,
            "summary": ai_response,
            "root_cause": root_cause,
            "suggestion": suggestion
        })

        return ai_response

    except Exception as e:
        return f"[Error during analysis: {str(e)}]"
