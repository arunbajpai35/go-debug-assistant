from backend.llm_schema import parse_v2_text, parse_v3_json


def test_parse_v2_text_extracts_named_fields():
    text = (
        "category: db\n"
        "root_cause: connection pool exhausted\n"
        "next_step: increase pool size to 50\n"
        "evidence: 10:00:00, 10:00:01\n"
        "confidence: high\n"
    )
    out = parse_v2_text(text)
    assert out["category"] == "db"
    assert out["root_cause"] == "connection pool exhausted"
    assert out["evidence"] == ["10:00:00", "10:00:01"]
    assert out["confidence"] == "high"


def test_parse_v2_text_tolerates_extra_whitespace_and_unknown_lines():
    text = (
        "  category :  auth   \n"
        "this line has no colon and should be ignored\n"
        "root_cause:   token expired\n"
    )
    out = parse_v2_text(text)
    assert out["category"] == "auth"
    assert out["root_cause"] == "token expired"


def test_parse_v2_text_accepts_json_array_evidence():
    out = parse_v2_text('evidence: ["t1", "t2", "t3"]\n')
    assert out["evidence"] == ["t1", "t2", "t3"]


def test_parse_v3_json_returns_dict():
    text = '{"category":"memory","root_cause":"oom","confidence":"high"}'
    out = parse_v3_json(text)
    assert out["category"] == "memory"
    assert out["confidence"] == "high"


def test_parse_v3_json_empty_dict_on_invalid_json():
    assert parse_v3_json("not json") == {}
    assert parse_v3_json("[1, 2, 3]") == {}  # not a dict
    assert parse_v3_json("") == {}
