import time
import random
import json
import os
import zmq

ZMQ_PUB_PORT = os.getenv("ZMQ_PUB_PORT", "5555")

class PhotodetectorDataStreamer:
    """
    Simulates hardware telemetry streams over a high-speed ZeroMQ broker.
    - Transient Phase: 25-30 Hz (~0.035s interval)
    - Nominal Phase: 1 Hz (1.0s interval)
    """
    def __init__(self, mode="transient"):
        self.mode = mode
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(f"tcp://*:{ZMQ_PUB_PORT}")
        print(f"[ZMQ Publisher] Bound and listening on tcp://*:{ZMQ_PUB_PORT}")

    def generate_sensor_readings(self) -> dict:
        base_temp = 25.0 + random.uniform(-0.5, 0.5)
        bias_v = 5.0
        optical_power_w = 0.001 + random.uniform(-0.0001, 0.0001)

        return {
            "temperature_c": round(base_temp, 2),
            "bias_voltage_v": round(bias_v, 2),
            "optical_power_w": round(optical_power_w, 6)
        }

    def start_streaming(self):
        interval = 0.035 if self.mode == "transient" else 1.0
        print(f"[Streamer] Continuous streaming started in '{self.mode}' mode via ZMQ...")
        
        while True:
            payload = self.generate_sensor_readings()
            # Publish message with topic prefix 'telemetry'
            message = f"telemetry {json.dumps(payload)}"
            self.socket.send_string(message)
            time.sleep(interval)

if __name__ == "__main__":
    time.sleep(2)
    streamer = PhotodetectorDataStreamer(mode="transient")
    streamer.start_streaming()