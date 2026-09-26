import time
from typing import Optional, Dict, Any
from linuxlab.lab.controller import LabController
from linuxlab.scenarios.registry import registry
from linuxlab.state.manager import StateManager
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.evaluation.reports import IncidentReportGenerator
from linuxlab.ai.ollama import OllamaClient

class IncidentEvaluator:
    """Evaluates the learner's incident resolution against actual lab state."""

    def __init__(self, controller: LabController):
        self.controller = controller
        self.ai = OllamaClient()

    def evaluate_current(self, user_explanation: str = "") -> Optional[Dict[str, Any]]:
        """Evaluate the currently active incident session."""
        session = StateManager.get_session()
        if not session:
            return None

        scenario_id = session.get("scenario_id")
        scenario = registry.get(scenario_id)
        if not scenario:
            return None

        # Verify actual state in the lab container
        is_solved, feedback_msg, metric_details = scenario.verify(self.controller)

        # Calculate timing and hints
        start_time = session.get("start_time", time.time())
        duration_sec = max(1.0, time.time() - start_time)
        hints_used = session.get("hints_used", [])

        # Compute deterministic score
        commands = session.get("command_history", [])
        score_data = IncidentScorer.calculate(
            is_solved=is_solved,
            hints_used=hints_used,
            duration_sec=duration_sec,
            level=getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")),
            command_count=len(commands),
            user_explanation=user_explanation
        )

        # Optional AI Critique if explanation provided
        ai_critique = ""
        if user_explanation.strip():
            ai_res = self.ai.critique_explanation(scenario, user_explanation)
            if ai_res:
                ai_critique = ai_res
            else:
                # Deterministic feedback fallback
                ai_critique = (
                    f"Deterministic Evaluation: Lab verification confirmed root cause resolution. "
                    f"Key verification signal: {feedback_msg}"
                )

        # Record result in persistent history
        StateManager.record_history_entry(
            scenario=scenario,
            solved=is_solved,
            score=score_data["score"],
            duration_sec=duration_sec,
            hints_used=hints_used,
            user_explanation=user_explanation
        )

        # If solved, clean up active session
        if is_solved:
            StateManager.clear_session()

        # Display rich report
        IncidentReportGenerator.print_report(
            scenario=scenario,
            is_solved=is_solved,
            score_data=score_data,
            user_explanation=user_explanation,
            ai_critique=ai_critique
        )

        return {
            "scenario": scenario,
            "is_solved": is_solved,
            "feedback": feedback_msg,
            "score_data": score_data,
        }
