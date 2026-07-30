import os                      # Used to access environment variables (e.g., API keys)
import json                    
import logging                 # Used for logging warnings and debug information
import requests                # Used to make HTTP requests to the Groq API
from typing import Dict, Any, Tuple  # Type hints for cleaner and more readable code
from physics_model import PhotodetectorPhysicsEngine  # Imports the physics simulation engine


try:
    from dotenv import load_dotenv
    load_dotenv()              # Reads variables from a .env file into environment variables
except ImportError:
    # Continue normally if python-dotenv is not installed
    pass


logger = logging.getLogger(__name__)
# Create a logger object for warning/error messages

class AICommandPlanner:
    """
    Behavioral AI & Command Validation Module.
    Interprets operational targets via natural language intent processing (Groq LLM / Fallback Engine)
    and validates noise/saturation safety before approving bias voltage commands to physical hardware.
    """
    
    
    # These are used if the LLM is unavailable.
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
        
        # This engine will later simulate the photodetector before any command is executed.
        self.engine = physics_engine

    def _fallback_keyword_parser(self, user_prompt: str) -> Tuple[str, float]:
        """
        Rule-based heuristic fallback parser.
        Executes if the LLM API call fails, times out, or has no API key set.
        """

        
        prompt_lower = user_prompt.lower()
        # This is a prompt to convert lowercase for case-insensitive keyword matching.
        
        for mode, keywords in self.KEYWORD_RULES.items():

            # If any keyword belonging to a mode exists in the prompt,
            # return that operating mode with moderate confidence.
            if any(kw in prompt_lower for kw in keywords):
                return mode, 0.75  
                
      
        return "balanced", 0.30  
          # If no keywords match, it will return the default balanced mode.

    def interpret_natural_language(self, user_prompt: str) -> Dict[str, Any]:
        """
        LLM / NLP Intent Interpreter.
        Translates natural language user operational goals into target gain modes using Groq LLM (LLaMA 3.3 70B).
        Falls back to rule-based keyword matching if the API key is missing or calls fail.
        """

        # This command is to retrieve the API key from environment variables.
        api_key = os.getenv("GROQ_API_KEY", "")

        # here we attempt an API request only if an API key exists.
        if api_key:
            try:
                # this is to check if Groq API endpoint is compatible with the OpenAI chat completion format.
                url = "https://api.groq.com/openai/v1/chat/completions"
                
                # we construct the request payload.
                payload = {

                    # this command specifies which LLM model should perform the task.
                    "model": "llama-3.3-70b-versatile",

                    # Conversation history will be provided to the model.
                    "messages": [
                        {
                            "role": "system",

                            # The System prompt instructs the LLM exactly how to behave here.
                            # It restricts the output to one of three operating modes and forces JSON output.
                            "content": (
                                "You are an intent interpreter for a photodetector sensor system. "
                                "Analyze the user prompt and map it to one of these modes: "
                                "['high_sensitivity', 'low_noise', 'balanced']. "
                                "Respond strictly in raw JSON format: {\"intent\": \"<mode>\", \"confidence\": <0.0-1.0>}"
                            )
                        },

                        # we give theUser's natural language command here.
                        {"role": "user", "content": user_prompt}
                    ],

                    # Temperature 0 ensures deterministic responses.
                    "temperature": 0.0,

                    # we ask the API to enforce JSON output.
                    "response_format": {"type": "json_object"}
                }
                
                # HTTP will request headers next.
                headers = {
                    "Authorization": f"Bearer {api_key}",   # API authentication
                    "Content-Type": "application/json",     # Request body format
                    "User-Agent": "opto-twin-core/1.0"      # Identifier for the application
                }

                # We then send POST request to Groq server.
                # Timeout help prevent waiting forever if the server is unavailable.
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                
                # Continue only if the API request succeeds.
                if response.status_code == 200:

                    # the next command helps convert the HTTP response into Python dictionary.
                    res_data = response.json()

                    # weextract the model's JSON string and convert it into a dictionary next
                    content = json.loads(res_data['choices'][0]['message']['content'])
                    
                    # it returns a structured interpretation result.
                    return {
                        "intent": content.get("intent", "balanced"),
                        "confidence": float(content.get("confidence", 0.9)),
                        "source": "LLM (Groq / LLaMA 3.3)",
                        "status": "success"
                    }
                else:
                    # Display API error details if request failed.
                    print(f"Groq API returned status code {response.status_code}: {response.text}")

            except Exception as e:
                # Print complete stack trace for debugging.
                import traceback
                print("=== FULL ERROR ===")
                traceback.print_exc()

                # Log warning and continue using fallback parser.
                logger.warning(f"Groq API call failed ({e}). Falling back to rule-based engine.")

        
        # If the API key does not exist or the API call failed,
        # we will use keyword matching instead.
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

        # Extract sensor values from telemetry dictionary.
        snr_db = state.get("snr_db", 0.0)
        health_pct = state.get("health_index_pct", 100.0)
        photocurrent_a = state.get("photocurrent_a", 0.0)

        # Highest priority:
        # If the sensor is already saturated, it will immediately switch to low-noise mode.
        if state.get("is_saturated", False):
            return "low_noise"

        # If health is poor or SNR has dropped, prioritize stable low-noise operation.
        if health_pct < 60.0 or snr_db < 20.0:
            return "low_noise"

        # Very small photocurrent indicates weak optical input. We then increase sensitivity by recommending higher gain.
        if photocurrent_a < 1e-6:
            return "high_sensitivity"

        # Otherwise it will operate in balanced mode.
        return "balanced"

    def validate_and_plan_bias(self, target_gain_mode: str, current_temp_c: float, expected_power_w: float) -> dict:
        """
        Validates whether target mode is safe from saturation/noise degradation.
        Returns planned safe bias voltage (Vb) and execution approval flag.
        """

        # Lookup table converting operating mode into its corresponding bias voltage.
        mode_bias_map = {
            "low_noise": 3.0,
            "balanced": 5.0,
            "high_sensitivity": 12.0
        }

        # Retrieve desired bias voltage and it will return to default to balanced bias if unknown mode is supplied.
        candidate_bias = mode_bias_map.get(target_gain_mode, 5.0)

        # We simulate detector behaviour BEFORE applying the command.
        # This acts as a digital twin safety check.
        simulated_state = self.engine.evaluate_state(
            temp_c=current_temp_c,
            bias_v=candidate_bias,
            optical_power_w=expected_power_w
        )

        # If the simulation predicts saturation, we reject the requested configuration.
        if simulated_state["is_saturated"]:

            # We then reduce bias voltage to a safer operating point.
            safe_bias = 2.0

            # Simulate again to verify the safer configuration.
            rechecked_state = self.engine.evaluate_state(current_temp_c, safe_bias, expected_power_w)

            # It returns rejected commands along with recommended safe bias.
            return {
                "approved": False,
                "reason": "Target configuration caused optical signal saturation. Recommended lower bias applied.",
                "assigned_bias_v": safe_bias,
                "simulated_state": rechecked_state
            }

        # If no saturation occurs,we approve the requested operating bias.
        return {
            "approved": True,
            "reason": "Target operating bias validated safe.",
            "assigned_bias_v": candidate_bias,
            "simulated_state": simulated_state
        }