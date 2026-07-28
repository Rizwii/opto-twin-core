import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/twin_engine")))

from main import app

client = TestClient(app)

def test_health_check_endpoint_pass():
    """Integration Test: Verifies API server health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "online", "service": "twin_engine"}

def test_update_state_endpoint_pass():
    """Integration Test: Tests telemetry state update contract."""
    payload = {
        "temperature_c": 30.0,
        "bias_voltage_v": 5.0,
        "optical_power_w": 0.001
    }
    response = client.post("/update_state", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "digital_twin_state" in data
    assert data["digital_twin_state"]["responsivity_a_w"] > 0

def test_invalid_telemetry_schema_fail():
    """Contract Test: Ensures API rejects missing or invalid fields."""
    invalid_payload = {
        "temperature_c": 30.0
        # Missing bias_voltage_v and optical_power_w
    }
    response = client.post("/update_state", json=invalid_payload)
    assert response.status_code == 422 # Unprocessable Entity