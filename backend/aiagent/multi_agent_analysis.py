import uuid
from scripts.sliding_window import load_logs, correlate_logs
from aiagent.prompts import agent_prompts
from aiagent.model import call_agent  # ✅ Handles env + Together client safely

def analyze_with_agents(log_windows):
    analysis_results = []

    AGENT_MODELS = {
        "root_cause_agent": "gpt-4o",
        "fix_suggester_agent": "gpt-4o",
        "impact_analyzer_agent": "gpt-4o"
    }

    for log_text in log_windows:
        log_result = {
            "log_text": log_text,
            "agents": {}
        }

        for agent, prompt in agent_prompts.items():
            print(f"🤖 Running agent: {agent}")
            model_name = AGENT_MODELS.get(agent, "mistralai/Mistral-7B-Instruct-v0.1")
            formatted_prompt = prompt.format(log_text)
            result = call_agent(formatted_prompt, model_name=model_name)
            log_result["agents"][agent] = result

        analysis_results.append(log_result)

    return analysis_results

def prepare_segments_from_logs(log_file_path: str):
    raw_logs = load_logs(log_file_path)
    correlated = correlate_logs(raw_logs)

    segments = []
    for trace_id, logs in correlated.items():
        log_chunk = "\n".join(f"[{log['timestamp']}] {log['message']}" for log in logs)
        segments.append({
            "id": str(uuid.uuid4()),
            "text": log_chunk
        })

    return segments

def format_windows(correlated_dict):
    formatted = []
    for trace_id, logs in correlated_dict.items():
        combined = "\n".join(f"[{log['timestamp']}] {log.get('level', '')}: {log.get('message', '')}" for log in logs)
        formatted.append(combined)
    return formatted
