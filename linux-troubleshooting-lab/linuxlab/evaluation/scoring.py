import time
from typing import List, Dict, Any, Optional

class IncidentScorer:
    """Calculates evaluation score (0-100) based on resolution, hint penalties, timing, and learning level."""

    BASE_SCORE = 100
    HINT_PENALTIES = {
        1: 5,   # Level 1 hint: -5 points
        2: 10,  # Level 2 hint: -10 points
        3: 15,  # Level 3 hint: -15 points
    }

    # Level-aware dimensional weight allocations
    LEVEL_WEIGHTS = {
        "EASY": {"technical": 70, "diagnosis": 15, "explanation": 15},
        "MODERATE": {"technical": 60, "diagnosis": 20, "explanation": 20},
        "FLUENT": {"technical": 60, "diagnosis": 20, "explanation": 20},
        "ADVANCED": {"technical": 50, "diagnosis": 25, "explanation": 25},
        "EXPERT": {"technical": 50, "diagnosis": 25, "explanation": 25},
    }

    @classmethod
    def calculate(
        cls,
        is_solved: bool,
        hints_used: List[int],
        duration_sec: float,
        explanation_quality_score: int = 0,
        level: str = "EASY",
        command_count: int = 0,
        user_explanation: str = "",
        dimensional_eval: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Calculates final score out of 100 with level-aware rules and dimensional breakdown.
        If unsolved, maximum score is 0.
        """
        level_upper = level.upper()
        weights = cls.LEVEL_WEIGHTS.get(level_upper, {"technical": 60, "diagnosis": 20, "explanation": 20})

        if not is_solved:
            return {
                "score": 0,
                "base": cls.BASE_SCORE,
                "hint_deduction": 0,
                "time_deduction": 0,
                "command_penalty": 0,
                "reasoning_bonus": 0,
                "breakdown": "Incident unresolved in lab environment.",
                "technical_resolution": "FAIL",
                "overall_verdict": "INCIDENT UNRESOLVED",
                "dimensional_breakdown": {
                    "technical": {"score": 0, "max": weights["technical"], "weight": f"{weights['technical']}%", "status": "FAIL"},
                    "diagnosis": {"score": 0, "max": weights["diagnosis"], "weight": f"{weights['diagnosis']}%", "status": "FAIL"},
                    "explanation": {"score": 0, "max": weights["explanation"], "weight": f"{weights['explanation']}%", "status": "FAIL"},
                }
            }

        score = cls.BASE_SCORE

        # Deduct for hints
        hint_deduction = sum(cls.HINT_PENALTIES.get(h, 10) for h in hints_used)
        score -= hint_deduction

        # Deduct for excessive resolution time (> 15 minutes = -5, > 30 minutes = -10)
        time_deduction = 0
        if duration_sec > 1800:
            time_deduction = 10
        elif duration_sec > 900:
            time_deduction = 5
        score -= time_deduction

        # For FLUENT, ADVANCED, EXPERT: command count is NOT rewarded.
        # Targeted troubleshooting is prioritized over brute-force trial and error.
        command_penalty = 0
        if level_upper in ["ADVANCED", "EXPERT"] and command_count > 40:
            command_penalty = 5
            score -= command_penalty

        # Reasoning bonus: rewarding thoughtful explanation of root cause and evidence
        reasoning_bonus = 0
        if user_explanation and len(user_explanation.strip()) > 20:
            # Automatic +5 reasoning bonus for articulating diagnosis
            reasoning_bonus = min(10, 5 + explanation_quality_score)
        elif explanation_quality_score > 0:
            reasoning_bonus = min(10, explanation_quality_score)

        score = max(0, min(100, score + reasoning_bonus))

        # Dimensional breakdown (Technical 50-70%, Diagnosis 15-25%, Explanation 15-25%)
        tech_status = "PASS" if is_solved else "FAIL"
        tech_base = weights["technical"]
        tech_score = max(0, tech_base - hint_deduction - time_deduction - command_penalty)

        diag_status = "PASS"
        diag_score = weights["diagnosis"]
        expl_status = "PASS"
        expl_score = weights["explanation"]

        if dimensional_eval and "dimensions" in dimensional_eval:
            dims = dimensional_eval["dimensions"]
            diag_status = dims.get("root_cause", {}).get("status", "PASS")
            if "PARTIAL" in diag_status:
                diag_score = max(5, int(weights["diagnosis"] * 0.6))
            elif diag_status in ["UNKNOWN", "FAIL"]:
                diag_score = max(0, int(weights["diagnosis"] * 0.2))

            expl_status = dims.get("explanation", {}).get("status", "PASS")
            if expl_status == "PARTIAL":
                expl_score = max(5, int(weights["explanation"] * 0.6))
            elif expl_status in ["NEEDS IMPROVEMENT", "FAIL"]:
                expl_score = max(0, int(weights["explanation"] * 0.2)) if user_explanation else 0

        return {
            "score": score,
            "base": cls.BASE_SCORE,
            "hint_deduction": hint_deduction,
            "time_deduction": time_deduction,
            "command_penalty": command_penalty,
            "reasoning_bonus": reasoning_bonus,
            "hints_count": len(hints_used),
            "command_count": command_count,
            "level": level_upper,
            "duration_sec": round(duration_sec, 1),
            "technical_resolution": "PASS",
            "overall_verdict": "INCIDENT RESOLVED",
            "dimensional_breakdown": {
                "technical": {"score": tech_score, "max": weights["technical"], "weight": f"{weights['technical']}%", "status": tech_status},
                "diagnosis": {"score": diag_score, "max": weights["diagnosis"], "weight": f"{weights['diagnosis']}%", "status": diag_status},
                "explanation": {"score": expl_score, "max": weights["explanation"], "weight": f"{weights['explanation']}%", "status": expl_status},
            }
        }
