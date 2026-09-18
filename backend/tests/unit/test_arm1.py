from unittest.mock import MagicMock, patch

from eval.arms.arm1_baseline_llm import _normalize_level, _parse_llm_json, run_arm1

from app.schemas.case import NormalisedCase


def test_normalize_level():
    assert _normalize_level("HIGH_RISK") == "HIGH_RISK"
    assert _normalize_level("high risk") == "HIGH_RISK"
    assert _normalize_level("caution") == "CAUTION"
    assert _normalize_level("LOW_CONCERN") == "LOW_CONCERN"
    assert _normalize_level("safe") == "LOW_CONCERN"


def test_parse_llm_json():
    sample = '''`json
    {
        "level": "HIGH_RISK",
        "reasons": ["Urgent language", "Suspicious link"]
    }
    `'''
    res = _parse_llm_json(sample)
    assert res["level"] == "HIGH_RISK"
    assert len(res["reasons"]) == 2


@patch("eval.arms.arm1_baseline_llm.Agent")
def test_run_arm1_contract(mock_agent_cls):
    mock_agent = MagicMock()
    mock_agent.return_value = '{"level": "HIGH_RISK", "reasons": ["suspicious"]}'
    mock_agent_cls.return_value = mock_agent

    case = NormalisedCase(
        case_id="c_test_1",
        input_types=["text"],
        text="Test scam message",
    )
    report = run_arm1(case)

    # Contract assertions
    assert report.case_id == "c_test_1"
    assert report.risk_level == "HIGH_RISK"
    assert report.evidence == []  # Contract: evidence list must be empty
    assert len(report.why) == 1
    assert report.why[0].evidence_ids == []
