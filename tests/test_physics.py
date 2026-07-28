import pytest
import sys
import os

# Ensure services directory is in Python path for test discovery
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/twin_engine")))

from physics_model import PhotodetectorPhysicsEngine

def test_responsivity_and_photocurrent_pass():
    """Unit Test: Validates physics calculation under nominal conditions (PASS)."""
    engine = PhotodetectorPhysicsEngine()
    state = engine.evaluate_state(temp_c=25.0, bias_v=5.0, optical_power_w=0.001)

    assert state["responsivity_a_w"] > 0
    assert state["photocurrent_a"] == pytest.approx(0.00091375, rel=1e-3)
    assert state["health_index_pct"] <= 100.0
    assert state["is_saturated"] is False

def test_negative_optical_power_fail():
    """Unit Test: Ensures system flags invalid negative optical power (FORCED FAIL/EXCEPTION)."""
    engine = PhotodetectorPhysicsEngine()
    with pytest.raises(ValueError, match="Optical power cannot be negative"):
        engine.evaluate_state(temp_c=25.0, bias_v=5.0, optical_power_w=-0.001)

def test_thermal_dark_current_drift_pass():
    """Unit Test: Verifies dark current increases exponentially with thermal stress (PASS)."""
    engine = PhotodetectorPhysicsEngine()
    cool_state = engine.evaluate_state(temp_c=20.0, bias_v=5.0, optical_power_w=0.001)
    hot_state = engine.evaluate_state(temp_c=75.0, bias_v=5.0, optical_power_w=0.001)

    assert hot_state["dark_current_a"] > cool_state["dark_current_a"]