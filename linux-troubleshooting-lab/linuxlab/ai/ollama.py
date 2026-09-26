import requests
from typing import Optional, Dict, Any, List
from linuxlab.config import OLLAMA_HOST, OLLAMA_MODEL

class OllamaClient:
    """Optional client for local LLM enhancement via Ollama."""

    def __init__(self, host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL):
        self.host = host.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        """Check if local Ollama daemon is active and responsive."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=1.5)
            if r.status_code == 200:
                models = r.json().get("models", [])
                # Return True if any model is available or daemon is up
                return True
            return False
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Return list of available installed models."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=1.5)
            if r.status_code == 200:
                return [m.get("name") for m in r.json().get("models", [])]
            return []
        except Exception:
            return []

    def generate(self, prompt: str, system: str = "") -> Optional[str]:
        """Generate response from local model, returning None on failure."""
        if not self.is_available():
            return None
        models = self.list_models()
        model_to_use = self.model
        if models and self.model not in models:
            # Fall back to first available model if preferred model isn't downloaded
            model_to_use = models[0]
        elif not models:
            return None

        try:
            payload = {
                "model": model_to_use,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 400
                }
            }
            r = requests.post(f"{self.host}/api/generate", json=payload, timeout=25.0)
            if r.status_code == 200:
                return r.json().get("response", "").strip()
            return None
        except Exception:
            return None

    def critique_explanation(self, scenario: Any, user_explanation: str) -> Optional[str]:
        """Provide a senior SRE critique of the user's diagnosis and reasoning."""
        if not user_explanation.strip():
            return None

        prompt = (
            f"Scenario Title: {scenario.title}\n"
            f"Category: {scenario.category}\n"
            f"Expected Root Cause: {scenario.expected_root_cause}\n"
            f"Expected Fix: {scenario.expected_fix}\n\n"
            f"Learner's Explanation of Root Cause and Fix:\n\"{user_explanation}\"\n\n"
            "As a Senior Staff SRE, evaluate their explanation in 3-4 bullet points: "
            "1. Did they identify the real technical root cause? "
            "2. Was their troubleshooting methodology sound? "
            "3. What production risk or blind spot should they keep in mind next time?"
        )
        system = "You are a pragmatic, senior Linux Staff Site Reliability Engineer mentoring a 2 YOE DevOps engineer. Be constructive, precise, and concise."
        return self.generate(prompt, system=system)
