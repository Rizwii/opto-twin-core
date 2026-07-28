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

# Initialize MQTT Client
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="TwinEngine")

def init_mqtt():
    try:
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"[MQTT] Connected successfully to broker at {MQTT_HOST}:{MQTT_PORT}")
    except Exception as err:
        print(f"[MQTT Error] Failed to connect: {err}")

def write_to_influx(temp_c: float, bias_v: float, state: dict):
    """Writes physics telemetry point to InfluxDB time-series database."""
    try:
        with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
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

            state = physics_engine.evaluate_state(
                temp_c=data["temperature_c"],
                bias_v=data["bias_voltage_v"],
                optical_power_w=data["optical_power_w"]
            )
            write_to_influx(data["temperature_c"], data["bias_voltage_v"], state)
        except Exception as e:
            print(f"[ZMQ Listener Error] {e}")

@app.on_event("startup")
def startup_event():
    init_mqtt()
    # Start ZMQ background listener
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

@app.post("/plan_command")
def plan_user_command(cmd: CommandInput):
    plan_result = ai_planner.validate_and_plan_bias(
        target_gain_mode=cmd.target_gain_mode,
        current_temp_c=cmd.current_temp_c,
        expected_power_w=cmd.expected_power_w
    )
    
    # Broadcast approved bias voltage command to hardware over MQTT
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