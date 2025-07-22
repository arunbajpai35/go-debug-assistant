from scripts.sliding_window import load_logs, correlate_logs
from scripts.multi_agent_reasoner import analyze_trace

def main():
    logs = load_logs("logs/sample.json")
    correlated = correlate_logs(logs, window_seconds=120)

    for trace_id, events in correlated.items():
        report = analyze_trace(trace_id, events)
        print("\n=== Multi-Agent Diagnosis ===")
        print(f"Trace ID: {report['trace_id']}")
        print(f"Summary: {report['summary']}")
        print(f"Root Cause: {report['root_cause']}")
        print(f"Recommendation: {report['recommendation']}")

if __name__ == "__main__":
    main()
