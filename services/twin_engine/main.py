from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from physics_model import PhotodetectorPhysicsEngine
from ai_planner import AICommandPlanner

app = FastAPI(title="Photodetector Digital Twin Engine", version="1.0.0")

# Initialize physics and AI planning modules
physics_engine = PhotodetectorPhysicsEngine()
ai_planner = AICommandPlanner(physics_engine)

class TelemetryInput(BaseModel):
    temperature_c: float
    bias_voltage_v: float
    optical_power_w: float

class CommandInput(BaseModel):
    target_gain_mode: str  # "low_noise", "balanced", or "high_sensitivity"
    current_temp_c: float
    expected_power_w: float

@app.get("/health")
def health_check():
    return {"status": "online", "service": "twin_engine"}

@app.post("/update_state")
def update_twin_state(data: TelemetryInput):
    """Processes incoming high-rate sensor streams into Digital Twin State."""
    try:
        state = physics_engine.evaluate_state(
            temp_c=data.temperature_c,
            bias_v=data.bias_voltage_v,
            optical_power_w=data.optical_power_w
        )
        return {
            "telemetry_input": data.dict(),
            "digital_twin_state": state
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

@app.post("/plan_command")
def plan_user_command(cmd: CommandInput):
    """LLM / Behavioral AI module validating bias commands before physical deployment."""
    plan_result = ai_planner.validate_and_plan_bias(
        target_gain_mode=cmd.target_gain_mode,
        current_temp_c=cmd.current_temp_c,
        expected_power_w=cmd.expected_power_w
    )
    return plan_result