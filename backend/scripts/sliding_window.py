import json
from datetime import datetime, timedelta
from collections import defaultdict

def load_logs(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def parse_iso8601(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")

def correlate_logs(logs, window_seconds=60):
    # Step 1: Parse timestamps and sort logs
    for log in logs:
        log['parsed_ts'] = parse_iso8601(log['timestamp'])
    logs.sort(key=lambda log: log['parsed_ts'])

    # Step 2: Get all unique trace IDs
    trace_ids = set(log['trace_id'] for log in logs if 'trace_id' in log)

    correlated = {}
    for trace_id in trace_ids:
        # Step 3: For each log with this trace_id, collect window
        related_logs = []
        trace_logs = [log for log in logs if log.get('trace_id') == trace_id]

        for log in trace_logs:
            center = log['parsed_ts']
            window_start = center - timedelta(seconds=window_seconds)
            window_end = center + timedelta(seconds=window_seconds)

            window_logs = [l for l in logs if window_start <= l['parsed_ts'] <= window_end]
            related_logs.extend(window_logs)

        # Step 4: Deduplicate logs and sort
        unique_logs = list({id(log): log for log in related_logs}.values())
        unique_logs.sort(key=lambda l: l['parsed_ts'])

        correlated[trace_id] = unique_logs

    return correlated
