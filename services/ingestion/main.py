import time
import random
import requests

TWIN_ENGINE_URL = "http://127.0.0.1:8000/update_state"

class PhotodetectorDataStreamer:
    """
    Simulates high-frequency hardware telemetry streams.
    - Transient Phase: 25-30 Hz (0.035s delay)
    - Nominal Phase: 1 Hz (1.0s delay)
    """
    def __init__(self, mode="nominal"):
        self.mode = mode

    def generate_sensor_readings(self) -> dict:
        # Simulate realistic noise and ambient thermal fluctuations
        base_temp = 25.0 + random.uniform(-0.5, 0.5)
        bias_v = 5.0
        optical_power_w = 0.001 + random.uniform(-0.0001, 0.0001)

        return {
            "temperature_c": round(base_temp, 2),
            "bias_voltage_v": round(bias_v, 2),
            "optical_power_w": round(optical_power_w, 6)
        }

    def start_streaming(self, duration_seconds: int = 5):
        interval = 0.035 if self.mode == "transient" else 1.0
        print(f"[Streamer] Starting data streaming in '{self.mode}' mode at interval {interval}s...")
        
        end_time = time.time() + duration_seconds
        samples_sent = 0

        while time.time() < end_time:
            payload = self.generate_sensor_readings()
            try:
                # Transmit stream payload to Twin Engine API
                response = requests.post(TWIN_ENGINE_URL, json=payload, timeout=2.0)
                if response.status_code == 200:
                    samples_sent += 1
            except requests.exceptions.RequestException:
                print("[Streamer Warning] Twin engine server unreachable.")

            time.sleep(interval)

        print(f"[Streamer] Completed stream session. Total samples ingested: {samples_sent}")

if __name__ == "__main__":
    streamer = PhotodetectorDataStreamer(mode="transient")
    streamer.start_streaming(duration_seconds=3)