"""structured llm response schema. used by prompt v3 (json_object mode) and as the
return shape from llm.analyze regardless of prompt version (older prompts emit free text;
the parser fills the dataclass best-effort and leaves missing fields as None)."""
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["db", "auth", "network", "memory", "config", "upstream", "cache", "kafka", "other"]
Confidence = Literal["high", "medium", "low"]


class StructuredAnalysis(BaseModel):
    """json schema sent to the llm in structured-output mode (v3)."""

    category: Category
    root_cause: str = Field(..., description="one sentence, name the specific failing component")
    next_step: str = Field(..., description="one concrete action, not 'investigate'")
    evidence: list[str] = Field(default_factory=list, description="log timestamps you relied on")
    confidence: Confidence


@dataclass
class AnalysisResult:
    """unified return type from llm.analyze. fields are nullable for older prompt versions
    that only produce free text."""

    raw_text: str
    model: str
    prompt_version: str
    category: str | None = None
    root_cause: str | None = None
    next_step: str | None = None
    evidence: list[str] = field(default_factory=list)
    confidence: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


_FIELD_RE = re.compile(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", re.IGNORECASE)


def parse_v2_text(text: str) -> dict:
    """best-effort parser for the v2 prompt's `key: value` format. tolerant of extra whitespace
    and ordering. unknown lines are ignored."""
    out: dict[str, str | list[str]] = {}
    for line in text.splitlines():
        m = _FIELD_RE.match(line)
        if not m:
            continue
        key = m.group(1).lower()
        val = m.group(2).strip()
        if key == "evidence":
            # accept comma-separated or json-array forms
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        out[key] = [str(x) for x in parsed]
                        continue
                except json.JSONDecodeError:
                    pass
            out[key] = [v.strip() for v in val.split(",") if v.strip()]
        else:
            out[key] = val
    return out


def parse_v3_json(text: str) -> dict:
    """v3 returns json. parse it; on failure return empty dict (caller leaves fields None)."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}
