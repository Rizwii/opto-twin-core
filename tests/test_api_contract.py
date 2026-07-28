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

def test_plan_command_endpoint_pass():
    """Integration Test: Tests command validation endpoint."""
    payload = {
        "target_gain_mode": "balanced",
        "current_temp_c": 25.0,
        "expected_power_w": 0.001
    }
    response = client.post("/plan_command", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "approved" in data
    assert data["approved"] is True

def test_natural_language_command_endpoint_pass():
    """Integration Test: Verifies LLM prompt interpretation endpoint."""
    payload = {
        "user_prompt": "Optimize system for minimal noise level",
        "current_temp_c": 25.0,
        "expected_power_w": 0.001
    }
    response = client.post("/plan_nl_command", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["interpreted_gain_mode"] == "low_noise"
    assert data["plan_result"]["approved"] is True