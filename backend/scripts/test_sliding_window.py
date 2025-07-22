from sliding_window import load_logs, correlate_logs
import pprint

if __name__ == "__main__":
    logs = load_logs("logs/sample.json")
    correlated = correlate_logs(logs, window_seconds=60)

    print(f"\n✅ Correlated {len(correlated)} trace groups:\n")

    for trace_id, group in correlated.items():
        print(f"\n🔹 Trace ID: {trace_id} ({len(group)} logs)")
        for log in group:
            print(f"  [{log['timestamp']}] {log['service']} - {log['level']} - {log['message']}")
