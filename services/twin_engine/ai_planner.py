import os
import json
import logging
import requests
from typing import Dict, Any, Tuple
from physics_model import PhotodetectorPhysicsEngine

# Load environment variables from local .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


class AICommandPlanner:
    """
    Behavioral AI & Command Validation Module.
    Interprets operational targets via natural language intent processing (Groq LLM / Fallback Engine)
    and validates noise/saturation safety before approving bias voltage commands to physical hardware.
    """
    
    # Fallback Keyword Rules
    KEYWORD_RULES = {
        "high_sensitivity": [
            "maximum sensitivity", "high gain", "faint", "weak signal", 
            "high sensitivity", "boost the gain", "dark conditions"
        ],
        "low_noise": [
            "low noise", "quiet mode", "precision mode", "minimal noise", 
            "thermal noise", "reduce jitter", "clean signal"
        ],
        "balanced": [
            "balanced", "default", "standard", "normal"
        ]
    }

    def __init__(self, physics_engine: PhotodetectorPhysicsEngine):
        self.engine = physics_engine

    def _fallback_keyword_parser(self, user_prompt: str) -> Tuple[str, float]:
        """
        Rule-based heuristic fallback parser.
        Executes if the LLM API call fails, times out, or has no API key set.
        """
        prompt_lower = user_prompt.lower()
        for mode, keywords in self.KEYWORD_RULES.items():
            if any(kw in prompt_lower for kw in keywords):
                return mode, 0.75  # Moderate confidence for keyword match
                
        return "balanced", 0.30  # Low confidence default fallback

    def interpret_natural_language(self, user_prompt: str) -> Dict[str, Any]:
        """
        LLM / NLP Intent Interpreter.
        Translates natural language user operational goals into target gain modes using Groq LLM (LLaMA 3.3 70B).
        Falls back to rule-based keyword matching if the API key is missing or calls fail.
        """
        api_key = os.getenv("GROQ_API_KEY", "")

        if api_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are an intent interpreter for a photodetector sensor system. "
                                "Analyze the user prompt and map it to one of these modes: "
                                "['high_sensitivity', 'low_noise', 'balanced']. "
                                "Respond strictly in raw JSON format: {\"intent\": \"<mode>\", \"confidence\": <0.0-1.0>}"
                            )
                        },
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                }
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "opto-twin-core/1.0"
                }

                # Using requests library to ensure consistent authorization handshake
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                
                if response.status_code == 200:
                    res_data = response.json()
                    content = json.loads(res_data['choices'][0]['message']['content'])
                    
                    return {
                        "intent": content.get("intent", "balanced"),
                        "confidence": float(content.get("confidence", 0.9)),
                        "source": "LLM (Groq / LLaMA 3.3)",
                        "status": "success"
                    }
                else:
                    print(f"Groq API returned status code {response.status_code}: {response.text}")

            except Exception as e:
                import traceback
                print("=== FULL ERROR ===")
                traceback.print_exc()
                logger.warning(f"Groq API call failed ({e}). Falling back to rule-based engine.")

        # Graceful Fallback Execution
        intent, confidence = self._fallback_keyword_parser(user_prompt)
        return {
            "intent": intent,
            "confidence": confidence,
            "source": "Rule-Based Fallback Engine",
            "status": "fallback" if api_key else "no_api_key"
        }

    def recommend_mode_from_state(self, state: dict) -> str:
        """
        Behavioral Model: Selects operational gain mode from ingested telemetry state.
        Reacts to live sensor data rather than user prompts.
        """
        snr_db = state.get("snr_db", 0.0)
        health_pct = state.get("health_index_pct", 100.0)
        photocurrent_a = state.get("photocurrent_a", 0.0)

        if state.get("is_saturated", False):
            return "low_noise"
        if health_pct < 60.0 or snr_db < 20.0:
            return "low_noise"
        if photocurrent_a < 1e-6:
            return "high_sensitivity"
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