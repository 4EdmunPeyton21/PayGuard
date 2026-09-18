from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent.investigator import InvestigationResult, TraceStep
from app.main import app
from app.schemas.evidence import Evidence, EvidenceLedger, Signal

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["dynamodb"] == "ok"


def test_get_nonexistent_case():
    response = client.get("/cases/nonexistent_123")
    assert response.status_code == 404
    response_trace = client.get("/cases/nonexistent_123/trace")
    assert response_trace.status_code == 404


def test_analyze_empty_request():
    response = client.post("/api/v1/analyze", json={})
    assert response.status_code == 400


def test_analyze_and_get_trace_end_to_end_mocked():
    """Validates the full flow from POST /api/v1/analyze to GET /cases/{id} and trace."""
    # Create synthetic investigation result
    mock_ledger = EvidenceLedger()
    mock_ledger.add(
        Evidence(
            id="E1",
            tool="signal_scan",
            signal=Signal.URGENCY_LANGUAGE,
            observed="Blocked today",
            interpretation="Urgency language found",
            direction="risk",
            strength="HIGH",
            confidence=0.9,
            quote="Blocked today",
            span=(0, 13),
        )
    )
    mock_trace = [
        TraceStep(
            tool="signal_scan",
            args={"text": "test"},
            result_type="ok",
            elapsed_ms=5,
            result_summary="1 signal found",
        ),
        TraceStep(
            tool="url_inspect",
            args={"url": "https://fake.in"},
            result_type="ok",
            elapsed_ms=10,
            result_summary="lookalike domain",
        ),
    ]
    mock_inv_res = InvestigationResult(
        ledger=mock_ledger,
        trace=mock_trace,
        tool_calls=2,
    )

    with patch("app.main.investigate", return_value=mock_inv_res):
        payload = {
            "text": "Dear customer, your account is blocked today: https://fake.in",
            "options": {"max_tool_calls": 6},
        }
        res = client.post("/api/v1/analyze", json=payload)
        assert res.status_code == 200
        report = res.json()
        assert "case_id" in report
        case_id = report["case_id"]
        assert report["risk_level"] in ["LOW_CONCERN", "CAUTION", "HIGH_RISK"]
        assert len(report["evidence"]) >= 1

        # Retrieve report via GET /cases/{id}
        get_res = client.get(f"/cases/{case_id}")
        assert get_res.status_code == 200
        stored_report = get_res.json()
        assert stored_report["case_id"] == case_id
        assert stored_report["headline"] == report["headline"]

        # Retrieve report via GET /api/v1/cases/{id}
        get_res_v1 = client.get(f"/api/v1/cases/{case_id}")
        assert get_res_v1.status_code == 200

        # Retrieve trace via GET /cases/{id}/trace
        trace_res = client.get(f"/cases/{case_id}/trace")
        assert trace_res.status_code == 200
        trace_data = trace_res.json()
        assert trace_data["case_id"] == case_id
        assert len(trace_data["trace"]) == 2
        assert trace_data["trace"][0]["tool"] == "signal_scan"
        assert trace_data["trace"][1]["tool"] == "url_inspect"

        # Retrieve trace via GET /api/v1/cases/{id}/trace
        trace_res_v1 = client.get(f"/api/v1/cases/{case_id}/trace")
        assert trace_res_v1.status_code == 200
