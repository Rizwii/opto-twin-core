import os
import json
import threading
import time
import zmq
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from physics_model import PhotodetectorPhysicsEngine
from ai_planner import AICommandPlanner
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

app = FastAPI(title="Photodetector Digital Twin Engine", version="1.0.0")

# Initialize physics engine and AI planner
physics_engine = PhotodetectorPhysicsEngine()
ai_planner = AICommandPlanner(physics_engine)

# Environment variables
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb_service:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-auth-token")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "opto-twin")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "photodetector_telemetry")

ZMQ_HOST = os.getenv("ZMQ_INGESTION_HOST", "ingestion")
ZMQ_PORT = os.getenv("ZMQ_INGESTION_PORT", "5555")

MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "mqtt_broker")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))

TWIN_STATE = {
    "device_id": None,
    "temperature_c": None,
    "bias_voltage_v": None,
    "optical_power_w": None,
    "timestamp": None,
    "physics_state": None,
    "recommended_gain_mode": None,
    "assigned_bias_v": None,
    "last_action": None,
    "updates_received": 0
}

# Single persistent InfluxDB Client instance across execution
influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# Initialize MQTT Client
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="TwinEngine")

def init_mqtt():
    """Retries connection until MQTT broker is accessible."""
    for attempt in range(5):
        try:
            mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
            mqtt_client.loop_start()
            print(f"[MQTT] Connected successfully to broker at {MQTT_HOST}:{MQTT_PORT}")
            return
        except Exception as err:
            print(f"[MQTT Warning] Connection attempt {attempt + 1}/5 failed: {err}. Retrying in 2s...")
            time.sleep(2)
    print("[MQTT Error] Could not connect to MQTT broker after retries.")

def write_to_influx(temp_c: float, bias_v: float, state: dict):
    """Writes physics telemetry point to InfluxDB time-series database."""
    try:
        point = Point("photodetector_state") \
            .tag("device_id", "pd_sensor_01") \
            .field("temperature_c", float(temp_c)) \
            .field("bias_voltage_v", float(bias_v)) \
            .field("responsivity_a_w", float(state["responsivity_a_w"])) \
            .field("dark_current_a", float(state["dark_current_a"])) \
            .field("photocurrent_a", float(state["photocurrent_a"])) \
            .field("snr_db", float(state["snr_db"])) \
            .field("health_index_pct", float(state["health_index_pct"]))
        
        write_api.write(bucket=INFLUXDB_BUCKET, record=point)
    except Exception as e:
        print(f"[InfluxDB Error] Write failed: {e}")

def zmq_telemetry_listener():
    """Background thread: Subscribes to high-speed ZMQ telemetry stream from ingestion service."""
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://{ZMQ_HOST}:{ZMQ_PORT}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "telemetry")
    print(f"[ZMQ Subscriber] Listening to tcp://{ZMQ_HOST}:{ZMQ_PORT}...")

    while True:
        try:
            raw_message = socket.recv_string()
            _, json_data = raw_message.split(" ", 1)
            data = json.loads(json_data)

            temp_c = data.get("temperature_c", 25.0)
            bias_v = data.get("bias_voltage_v", 5.0)
            optical_power_w = data.get("optical_power_w", data.get("power_w", 0.001))

            state = physics_engine.evaluate_state(
                temp_c=temp_c,
                bias_v=bias_v,
                optical_power_w=optical_power_w
            )
            write_to_influx(temp_c, bias_v, state)

            recommended_mode = ai_planner.recommend_mode_from_state(state)

            TWIN_STATE["device_id"] = data.get("device_id")
            TWIN_STATE["temperature_c"] = temp_c
            TWIN_STATE["bias_voltage_v"] = bias_v
            TWIN_STATE["optical_power_w"] = optical_power_w
            TWIN_STATE["timestamp"] = data.get("timestamp")
            TWIN_STATE["physics_state"] = state
            TWIN_STATE["updates_received"] += 1

            if recommended_mode != TWIN_STATE["recommended_gain_mode"]:
                plan_result = ai_planner.validate_and_plan_bias(
                    target_gain_mode=recommended_mode,
                    current_temp_c=temp_c,
                    expected_power_w=optical_power_w
                )
                TWIN_STATE["recommended_gain_mode"] = recommended_mode
                TWIN_STATE["assigned_bias_v"] = plan_result["assigned_bias_v"]
                TWIN_STATE["last_action"] = plan_result["reason"]

                payload = json.dumps({
                    "assigned_bias_v": plan_result["assigned_bias_v"],
                    "gain_mode": recommended_mode,
                    "approved": plan_result["approved"],
                    "source": "behavioral_model"
                })
                mqtt_client.publish("hardware/bias_command", payload)
                print(f"[Behavioral Model] Telemetry-driven mode change -> {recommended_mode} | bias {plan_result['assigned_bias_v']} V")
        except Exception as e:
            print(f"[ZMQ Listener Error] {e}")

@app.on_event("startup")
def startup_event():
    init_mqtt()
    listener_thread = threading.Thread(target=zmq_telemetry_listener, daemon=True)
    listener_thread.start()

# Data Transfer Models
class CommandInput(BaseModel):
    target_gain_mode: str
    current_temp_c: float
    expected_power_w: float

class NaturalLanguageCommandInput(BaseModel):
    user_prompt: str
    current_temp_c: float
    expected_power_w: float

@app.get("/health")
def health_check():
    return {"status": "online", "service": "twin_engine"}

@app.get("/twin_state")
def get_twin_state():
    """Returns the live digital twin state derived from ingested telemetry and the behavioral model's response to it."""
    return TWIN_STATE

@app.post("/plan_command")
def plan_user_command(cmd: CommandInput):
    plan_result = ai_planner.validate_and_plan_bias(
        target_gain_mode=cmd.target_gain_mode,
        current_temp_c=cmd.current_temp_c,
        expected_power_w=cmd.expected_power_w
    )
    
    if plan_result["approved"]:
        payload = json.dumps({"assigned_bias_v": plan_result["assigned_bias_v"]})
        mqtt_client.publish("hardware/bias_command", payload)
        print(f"[MQTT Published] Approved bias command sent: {payload}")

    return plan_result

@app.post("/plan_nl_command")
def plan_natural_language_command(cmd: NaturalLanguageCommandInput):
    """LLM Endpoint: Translates plain text user prompt to operational gain mode and executes planning."""
    gain_mode = ai_planner.interpret_natural_language(cmd.user_prompt)
    plan_result = ai_planner.validate_and_plan_bias(
        target_gain_mode=gain_mode,
        current_temp_c=cmd.current_temp_c,
        expected_power_w=cmd.expected_power_w
    )
    
    if plan_result["approved"]:
        payload = json.dumps({"assigned_bias_v": plan_result["assigned_bias_v"]})
        mqtt_client.publish("hardware/bias_command", payload)

    return {
        "interpreted_gain_mode": gain_mode,
        "plan_result": plan_result
    }