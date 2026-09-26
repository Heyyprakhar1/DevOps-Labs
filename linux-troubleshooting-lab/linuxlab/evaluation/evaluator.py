import time
from typing import Optional, Dict, Any, List
from linuxlab.lab.controller import LabController
from linuxlab.scenarios.registry import registry
from linuxlab.state.manager import StateManager
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.evaluation.reports import IncidentReportGenerator
from linuxlab.evaluation.evidence import EvidenceCollector
from linuxlab.evaluation.dimensional import DimensionalEvaluator
from linuxlab.db import db
from linuxlab.ai.ollama import OllamaClient

class IncidentEvaluator:
    """Evaluates the learner's incident resolution across four dimensions with machine evidence."""

    def __init__(self, controller: LabController):
        self.controller = controller
        self.ai = OllamaClient()

    def evaluate_session(
        self,
        session: Dict[str, Any],
        scenario: Any,
        user_explanation: str = ""
    ) -> Dict[str, Any]:
        """
        Core evaluation method determining resolution via machine check of sandbox state,
        evaluating four dimensions independently, and compiling machine evidence.
        """
        # 1. Inspect ground-truth state of the sandbox container
        is_solved, feedback_msg, metric_details = scenario.verify(self.controller)

        # 2. Timing and hints
        start_time = session.get("start_time", time.time())
        duration_sec = max(1.0, time.time() - start_time)
        hints_used = session.get("hints_used", [])
        commands = session.get("command_history", [])
        sc_level = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()

        # 3. Capture after evidence and compare with before state
        after_evidence = EvidenceCollector.capture(self.controller, scenario)
        before_evidence = session.get("initial_evidence") or EvidenceCollector.get_baseline_evidence(scenario)
        evidence = EvidenceCollector.compare(before_evidence, after_evidence, scenario, is_solved)

        # 4. Multi-dimensional evaluation (System State, Root Cause, Remediation, Explanation)
        dimensional_eval = DimensionalEvaluator.evaluate(
            scenario=scenario,
            is_solved=is_solved,
            feedback_msg=feedback_msg,
            user_explanation=user_explanation,
            command_history=commands,
            duration_sec=duration_sec,
            level=sc_level
        )

        # 5. Compute level-aware score with dimensional breakdown
        score_data = IncidentScorer.calculate(
            is_solved=is_solved,
            hints_used=hints_used,
            duration_sec=duration_sec,
            level=sc_level,
            command_count=len(commands),
            user_explanation=user_explanation,
            dimensional_eval=dimensional_eval
        )

        # 6. Optional AI Critique
        ai_critique = ""
        explanation = user_explanation.strip() if user_explanation else ""
        if explanation:
            ai_res = self.ai.critique_explanation(scenario, explanation)
            if ai_res:
                ai_critique = ai_res
            else:
                ai_critique = (
                    f"Deterministic Verification: System state confirms root cause resolution. "
                    f"Key verification signal: {feedback_msg}"
                )

        # 7. Structured Post-Mortem matching the level
        structured_postmortem = IncidentReportGenerator.get_structured_sections(scenario)

        # 8. Record in persistent history (User DB or legacy StateManager)
        user_id = session.get("user_id")
        if user_id:
            try:
                db.record_attempt(
                    user_id=user_id,
                    scenario_id=scenario.id,
                    category=getattr(scenario, "category", ""),
                    level=sc_level,
                    difficulty=getattr(scenario, "difficulty", sc_level),
                    status="SOLVED" if is_solved else "UNRESOLVED",
                    score=score_data["score"],
                    duration_sec=duration_sec,
                    hints_used=hints_used,
                    command_history=commands,
                    user_explanation=user_explanation,
                    technical_resolution=dimensional_eval.get("technical_resolution", "PASS" if is_solved else "FAIL"),
                    overall_verdict=dimensional_eval.get("overall_verdict", "INCIDENT RESOLVED" if is_solved else "INCIDENT UNRESOLVED"),
                    dimensions=dimensional_eval.get("dimensions", {}),
                    evidence=evidence,
                    postmortem=structured_postmortem
                )
                if is_solved:
                    db.close_incident_session(user_id, status="completed")
            except Exception as e:
                import logging
                logging.getLogger("linuxlab.evaluator").error(f"Failed to record attempt in DB: {e}")
        else:
            StateManager.record_history_entry(
                scenario=scenario,
                solved=is_solved,
                score=score_data["score"],
                duration_sec=duration_sec,
                hints_used=hints_used,
                user_explanation=user_explanation,
                dimensional_data=dimensional_eval
            )
            if is_solved:
                StateManager.clear_session()

        return {
            "scenario": scenario,
            "is_solved": is_solved,
            "technical_resolution": dimensional_eval["technical_resolution"],
            "overall_verdict": dimensional_eval["overall_verdict"],
            "overall_message": dimensional_eval["overall_message"],
            "explanation_feedback": dimensional_eval["explanation_feedback"],
            "dimensions": dimensional_eval["dimensions"],
            "evidence": evidence,
            "feedback_msg": feedback_msg,
            "metric_details": metric_details,
            "score": score_data["score"],
            "breakdown": score_data,
            "level": sc_level,
            "expected_root_cause": scenario.expected_root_cause,
            "expected_fix": scenario.expected_fix,
            "learning_points": scenario.learning_points,
            "structured_postmortem": structured_postmortem,
            "user_explanation": user_explanation,
            "ai_critique": ai_critique,
            "command_history": commands,
            "duration_sec": round(duration_sec, 1),
        }

    def evaluate_current(self, user_explanation: str = "") -> Optional[Dict[str, Any]]:
        """Evaluate the currently active incident session and display terminal report."""
        session = StateManager.get_session()
        if not session:
            return None

        scenario_id = session.get("scenario_id")
        scenario = registry.get(scenario_id)
        if not scenario:
            return None

        result = self.evaluate_session(session, scenario, user_explanation=user_explanation)

        # Display rich CLI report
        IncidentReportGenerator.print_report(
            scenario=scenario,
            is_solved=result["is_solved"],
            score_data=result["breakdown"],
            user_explanation=user_explanation,
            ai_critique=result.get("ai_critique", ""),
            dimensional_data=result,
            evidence=result.get("evidence")
        )

        return result
