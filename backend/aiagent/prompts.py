# aiagent/prompts.py

agent_prompts = {
    "root_cause_agent": """You are a root cause analysis agent. Analyze the following logs and identify the most likely root cause of the issue:

{}
""",

    "fix_suggester_agent": """You are a fix suggestion agent. Analyze the following logs and suggest a fix or resolution for the issue:

{}
""",

    "impact_analyzer_agent": """You are an impact analysis agent. Analyze the following logs and assess the potential or actual impact of the issue on users or systems:

{}
"""
}
