from physics_model import PhotodetectorPhysicsEngine

class AICommandPlanner:
    """
    Behavioral AI & Command Validation Module.
    Interprets operational targets via natural language intent processing and
    validates noise/saturation safety before approving bias voltage commands to physical hardware.
    """
    def __init__(self, physics_engine: PhotodetectorPhysicsEngine):
        self.engine = physics_engine

    def interpret_natural_language(self, user_prompt: str) -> str:
        """
        LLM / NLP Intent Interpreter.
        Translates natural language user operational goals into target gain modes.
        """
        prompt_lower = user_prompt.lower()
        
        if any(keyword in prompt_lower for keyword in ["noise", "quiet", "precision", "clean", "low noise"]):
            return "low_noise"
        elif any(keyword in prompt_lower for keyword in ["sensitive", "high gain", "faint", "weak", "sensitivity"]):
            return "high_sensitivity"
        else:
            return "balanced"

    def validate_and_plan_bias(self, target_gain_mode: str, current_temp_c: float, expected_power_w: float) -> dict:
        """
        Validates whether target mode is safe from saturation/noise degradation.
        Returns planned safe bias voltage (Vb) and execution approval flag.
        """
        # Mapping mode intent to candidate bias voltages
        mode_bias_map = {
            "low_noise": 3.0,
            "balanced": 5.0,
            "high_sensitivity": 12.0
        }

        candidate_bias = mode_bias_map.get(target_gain_mode, 5.0)

        # Pre-execution simulation using physics engine
        simulated_state = self.engine.evaluate_state(
            temp_c=current_temp_c,
            bias_v=candidate_bias,
            optical_power_w=expected_power_w
        )

        # Saturation and safety evaluation rule
        if simulated_state["is_saturated"]:
            # Recalculate to safe lower bias if candidate causes optical saturation
            safe_bias = 2.0
            rechecked_state = self.engine.evaluate_state(current_temp_c, safe_bias, expected_power_w)
            return {
                "approved": False,
                "reason": "Target configuration caused optical signal saturation. Recommended lower bias applied.",
                "assigned_bias_v": safe_bias,
                "simulated_state": rechecked_state
            }

        return {
            "approved": True,
            "reason": "Target operating bias validated safe.",
            "assigned_bias_v": candidate_bias,
            "simulated_state": simulated_state
        }