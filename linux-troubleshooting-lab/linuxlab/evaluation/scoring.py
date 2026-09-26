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

    @classmethod
    def calculate(
        cls,
        is_solved: bool,
        hints_used: List[int],
        duration_sec: float,
        explanation_quality_score: int = 0,
        level: str = "EASY",
        command_count: int = 0,
        user_explanation: str = ""
    ) -> Dict[str, Any]:
        """
        Calculates final score out of 100 with level-aware rules.
        If unsolved, maximum score is 0.
        """
        if not is_solved:
            return {
                "score": 0,
                "base": cls.BASE_SCORE,
                "hint_deduction": 0,
                "time_deduction": 0,
                "command_penalty": 0,
                "reasoning_bonus": 0,
                "breakdown": "Incident unresolved in lab environment.",
            }

        score = cls.BASE_SCORE
        level_upper = level.upper()

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
        }
