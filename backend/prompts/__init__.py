"""prompt registry. each version is a frozen tuple (system, user_template) that takes
named placeholders {window} and {log_text}.

versions are append-only — never edit a published version, add a new one and switch the
PROMPT_VERSION env var. eval results are tagged with the version they ran against."""
from backend.prompts import v1, v2, v3

PROMPTS: dict[str, tuple[str, str]] = {
    "v1": (v1.SYSTEM, v1.USER_TEMPLATE),
    "v2": (v2.SYSTEM, v2.USER_TEMPLATE),
    "v3": (v3.SYSTEM, v3.USER_TEMPLATE),
}

# versions whose output is structured json (parsed via llm_schema.parse_v3_json)
STRUCTURED_VERSIONS: set[str] = {"v3"}


def get(version: str) -> tuple[str, str]:
    if version not in PROMPTS:
        raise KeyError(f"unknown prompt version: {version}; registered: {list(PROMPTS)}")
    return PROMPTS[version]
