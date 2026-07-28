import time
import os
import requests
from pxr import Usd, UsdGeom, Gf

# Configuration
TWIN_ENGINE_URL = os.getenv("TWIN_ENGINE_URL", "http://localhost:8000/plan_command")
STAGE_PATH = os.getenv("USD_STAGE_PATH", "omniverse://localhost/Projects/OptoTwin/sensor_stage.usd")
SENSOR_PRIM_PATH = "/World/Photodetector_Sensor"

def fetch_telemetry_state():
    """Polls the twin engine or telemetry source for current state metrics."""
    payload = {
        "target_gain_mode": "balanced",
        "current_temp_c": 25.0,
        "expected_power_w": 0.001
    }
    try:
        response = requests.post(TWIN_ENGINE_URL, json=payload, timeout=1.0)
        if response.status_code == 200:
            data = response.json()
            return data.get("simulated_state", {})
    except Exception as e:
        print(f"[Omniverse Bridge Warning] Telemetry fetch skipped: {e}")
    return None

def update_usd_viewport(stage, prim_path, state):
    """
    Updates dynamic 3D visual attributes on the sensor Prim based on physical state:
    - SNR / Health Index maps to RGB display color (Green = Healthy, Red = Degraded).
    """
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        print(f"[Omniverse Bridge] Prim not found at path: {prim_path}")
        return

    health = state.get("health_index_pct", 100.0) / 100.0
    
    # Map Health Index to RGB Color: Red channel increases as health drops
    dynamic_color = Gf.Vec3f(1.0 - health, health, 0.0)

    gprim = UsdGeom.Gprim(prim)
    gprim.GetDisplayColorAttr().Set([dynamic_color])

    print(f"[Omniverse Bridge Sync] Health: {health*100:.1f}% | SNR: {state.get('snr_db', 0):.2f} dB -> RGB: {dynamic_color}")

def main():
    print(f"[Omniverse Bridge] Connecting to USD Stage at: {STAGE_PATH}")
    try:
        stage = Usd.Stage.Open(STAGE_PATH)
    except Exception as e:
        print(f"[Omniverse Bridge Error] Could not open USD stage: {e}")
        return

    while True:
        state = fetch_telemetry_state()
        if state:
            update_usd_viewport(stage, SENSOR_PRIM_PATH, state)
            stage.Save()
        time.sleep(0.1)  # ~10 Hz update loop for real-time viewport feedback

if __name__ == "__main__":
    main()