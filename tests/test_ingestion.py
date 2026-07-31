import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/ingestion")))

from main import PhotodetectorDataStreamer

@patch("main.zmq.Context")
@patch("main.mqtt.Client")
def test_generate_sensor_readings_format(mock_mqtt, mock_zmq):
    """Unit Test: Ensures ingestion telemetry produces correct data types and keys."""
    streamer = PhotodetectorDataStreamer(mode="transient")
    reading = streamer.generate_sensor_readings()

    assert "device_id" in reading
    assert "temperature_c" in reading
    assert "bias_voltage_v" in reading
    assert "optical_power_w" in reading
    assert "timestamp" in reading
    
    assert reading["device_id"] == "pd_sensor_01"
    assert isinstance(reading["temperature_c"], float)
    assert reading["bias_voltage_v"] == 5.0
    assert isinstance(reading["optical_power_w"], float)

@patch("main.zmq.Context")
@patch("main.mqtt.Client")
def test_optical_power_range(mock_mqtt, mock_zmq):
    """Unit Test: Verifies optical power stays within the expected simulated bounds."""
    streamer = PhotodetectorDataStreamer(mode="transient")
    reading = streamer.generate_sensor_readings()
    
    # Base is 0.001 with a +/- 0.0001 jitter
    assert 0.0009 <= reading["optical_power_w"] <= 0.0011