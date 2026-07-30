import time
import random
import json
import os
import zmq
import paho.mqtt.client as mqtt

ZMQ_PUB_PORT = os.getenv("ZMQ_PUB_PORT", "5555")
MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "mqtt_broker")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))

class PhotodetectorDataStreamer:
    """
    Simulates hardware telemetry streams over ZeroMQ and MQTT brokers.
    - Transient Phase: 25-30 Hz (~0.035s interval)
    - Nominal Phase: 1 Hz (1.0s interval)
    """
    def __init__(self, mode="transient"):
        self.mode = mode
        
        # Initialize ZeroMQ Publisher
        self.context = zmq.Context()
        self.zmq_socket = self.context.socket(zmq.PUB)
        self.zmq_socket.bind(f"tcp://*:{ZMQ_PUB_PORT}")
        print(f"[ZMQ Publisher] Bound and listening on tcp://*:{ZMQ_PUB_PORT}")

        # Initialize MQTT Publisher
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="IngestionStreamer")
        self.init_mqtt()

    def init_mqtt(self):
        """Continuously retries connection to MQTT broker until successful."""
        while True:
            try:
                self.mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
                self.mqtt_client.loop_start()
                print(f"[MQTT Publisher] Connected successfully to {MQTT_HOST}:{MQTT_PORT}")
                break  # Break out of the loop once connected
            except Exception as e:
                print(f"[MQTT Publisher Warning] Broker not ready, retrying in 3 seconds... ({e})")
                time.sleep(3)

    def generate_sensor_readings(self) -> dict:
        base_temp = 25.0 + random.uniform(-0.5, 0.5)
        bias_v = 5.0
        optical_power_w = 0.001 + random.uniform(-0.0001, 0.0001)

        return {
            "device_id": "pd_sensor_01",
            "temperature_c": round(base_temp, 2),
            "bias_voltage_v": round(bias_v, 2),
            "optical_power_w": round(optical_power_w, 6),
            "timestamp": time.time()
        }

    def start_streaming(self):
        interval = 0.035 if self.mode == "transient" else 1.0
        print(f"[Streamer] Continuous telemetry streaming started in '{self.mode}' mode...")
        
        try:
            while True:
                payload = self.generate_sensor_readings()
                json_payload = json.dumps(payload)

                # 1. ZeroMQ Broadcast (High-Speed Pub/Sub)
                message = f"telemetry {json_payload}"
                self.zmq_socket.send_string(message)

                # 2. MQTT Topic Publish (Telemetry Topic)
                try:
                    result = self.mqtt_client.publish("telemetry/pd_sensor_01", json_payload)
                    if result.rc != mqtt.MQTT_ERR_SUCCESS:
                        print(f"[MQTT Publish Warning] Return code: {result.rc}")
                except Exception as e:
                    print(f"[MQTT Publish Error] {e}")

                time.sleep(interval)
        except KeyboardInterrupt:
            print("[Streamer] Stopping telemetry streamer...")
        finally:
            self.zmq_socket.close()
            self.context.term()
            self.mqtt_client.loop_stop()

if __name__ == "__main__":
    time.sleep(2)
    streamer = PhotodetectorDataStreamer(mode="transient")
    streamer.start_streaming()