from sliding_window import load_logs, correlate_logs
from multi_agent_analysis import analyze_with_agents

if __name__ == "__main__":
    logs = load_logs("logs/sample.json")
    correlated = correlate_logs(logs, window_seconds=60)

    for trace_id, group in correlated.items():
        print(f"\n🧠 Analyzing Trace ID: {trace_id} with {len(group)} logs")

        response = analyze_with_agents(group)
        print(f"\n📌 AI Diagnosis for {trace_id}:\n{response}")
