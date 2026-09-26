import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from linuxlab.config import HISTORY_FILE, SESSION_FILE, CATEGORIES

class StateManager:
    """Manages persistent incident history and active troubleshooting sessions."""

    @classmethod
    def get_session(cls) -> Optional[Dict[str, Any]]:
        """Return active incident session if one exists."""
        if not SESSION_FILE.exists():
            return None
        try:
            with open(SESSION_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def start_session(cls, scenario_id: str, initial_evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start a new incident session."""
        session_data = {
            "scenario_id": scenario_id,
            "start_time": time.time(),
            "hints_used": [],
            "command_history": [],
            "status": "active",
            "initial_evidence": initial_evidence or {},
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(session_data, f, indent=2)
        return session_data

    @classmethod
    def record_hint(cls, hint_level: int):
        """Record that a hint level was accessed in the active session."""
        session = cls.get_session()
        if session:
            hints = session.get("hints_used", [])
            if hint_level not in hints:
                hints.append(hint_level)
                session["hints_used"] = hints
                with open(SESSION_FILE, "w") as f:
                    json.dump(session, f, indent=2)

    @classmethod
    def record_command(cls, command: str):
        """Record a command entered by the learner during the incident."""
        session = cls.get_session()
        if session and command.strip():
            cmds = session.get("command_history", [])
            ts = datetime.now().strftime("%H:%M:%S")
            cmds.append(f"{ts}  {command.strip()}")
            session["command_history"] = cmds
            try:
                with open(SESSION_FILE, "w") as f:
                    json.dump(session, f, indent=2)
            except Exception:
                pass

    @classmethod
    def clear_session(cls):
        """Remove active session file."""
        if SESSION_FILE.exists():
            try:
                SESSION_FILE.unlink()
            except Exception:
                pass

    @classmethod
    def load_history(cls) -> List[Dict[str, Any]]:
        """Load list of past incident records."""
        if not HISTORY_FILE.exists():
            return []
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def record_history_entry(
        cls,
        scenario: Any,
        solved: bool,
        score: int,
        duration_sec: float,
        hints_used: List[int],
        user_explanation: str = "",
        dimensional_data: Optional[Dict[str, Any]] = None
    ):
        """Append an incident result to history.json."""
        history = cls.load_history()
        lvl = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()
        entry = {
            "scenario_id": scenario.id,
            "category": scenario.category,
            "difficulty": getattr(scenario, "difficulty", lvl),
            "level": lvl,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "solved": solved,
            "score": score,
            "hints_count": len(hints_used),
            "hints_used": hints_used,
            "duration_sec": round(duration_sec, 1),
            "user_explanation": user_explanation,
        }
        if dimensional_data:
            entry["technical_resolution"] = dimensional_data.get("technical_resolution", "PASS" if solved else "FAIL")
            entry["overall_verdict"] = dimensional_data.get("overall_verdict", "INCIDENT RESOLVED" if solved else "INCIDENT UNRESOLVED")
            entry["dimensions"] = dimensional_data.get("dimensions", {})
        history.append(entry)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)

    @classmethod
    def get_recent_scenario_ids(cls, count: int = 5) -> List[str]:
        """Return list of most recently attempted scenario IDs."""
        history = cls.load_history()
        return [entry["scenario_id"] for entry in history[-count:]]

    @classmethod
    def calculate_progress(cls) -> Dict[str, Any]:
        """Aggregate stats across history including progressive levels."""
        history = cls.load_history()
        total_incidents = len(history)
        solved_count = sum(1 for e in history if e.get("solved", False))
        total_score = sum(e.get("score", 0) for e in history)
        avg_score = round(total_score / total_incidents, 1) if total_incidents > 0 else 0
        total_hints = sum(e.get("hints_count", 0) for e in history)

        # 1. Level Mastery Breakdown
        from linuxlab.config import LEVELS
        level_stats: Dict[str, Dict[str, Any]] = {
            lvl: {"attempted": 0, "solved": 0, "total_score": 0} for lvl in LEVELS
        }
        for entry in history:
            lvl = entry.get("level", entry.get("difficulty", "EASY")).upper()
            if lvl not in level_stats:
                # Map legacy difficulties if present
                if lvl == "2YOE":
                    lvl = "MODERATE"
                elif lvl == "PRODUCTION":
                    lvl = "EXPERT"
                else:
                    lvl = "EASY"
            level_stats[lvl]["attempted"] += 1
            if entry.get("solved"):
                level_stats[lvl]["solved"] += 1
            level_stats[lvl]["total_score"] += entry.get("score", 0)

        levels_breakdown = {}
        for lvl in LEVELS:
            data = level_stats[lvl]
            att = data["attempted"]
            sol = data["solved"]
            score_avg = round(data["total_score"] / att, 1) if att > 0 else 0
            rate = round((sol / att) * 100) if att > 0 else 0
            # Progress bar representation (e.g., 8 blocks out of 10)
            # Solved count / target (5 scenarios per level) capped at 100%
            target = 5
            progress_pct = min(100, round((sol / target) * 100))
            filled = round((progress_pct / 100) * 10)
            bar = ("█" * filled) + ("░" * (10 - filled))

            levels_breakdown[lvl] = {
                "attempted": att,
                "solved": sol,
                "rate": rate,
                "avg_score": score_avg,
                "progress_pct": progress_pct,
                "bar": bar,
            }

        # Determine Recommended Next Level
        recommended_level = "EASY"
        for lvl in LEVELS:
            if levels_breakdown[lvl]["solved"] < 3 or levels_breakdown[lvl]["rate"] < 70:
                recommended_level = lvl
                break
        else:
            recommended_level = "EXPERT"

        # 2. Category breakdown
        cat_stats: Dict[str, Dict[str, Any]] = {c: {"attempted": 0, "solved": 0, "total_score": 0} for c in CATEGORIES}
        for entry in history:
            cat = entry.get("category", "unknown").lower()
            if cat not in cat_stats:
                cat_stats[cat] = {"attempted": 0, "solved": 0, "total_score": 0}
            cat_stats[cat]["attempted"] += 1
            if entry.get("solved"):
                cat_stats[cat]["solved"] += 1
            cat_stats[cat]["total_score"] += entry.get("score", 0)

        breakdown = {}
        for cat, data in cat_stats.items():
            att = data["attempted"]
            sol = data["solved"]
            score_avg = round(data["total_score"] / att, 1) if att > 0 else 0
            rate = round((sol / att) * 100) if att > 0 else 0
            breakdown[cat] = {
                "attempted": att,
                "solved": sol,
                "rate": rate,
                "avg_score": score_avg,
            }

        # Identify weakest areas (where attempted > 0 and rate < 80% or low score)
        attempted_cats = [(cat, d["avg_score"]) for cat, d in breakdown.items() if d["attempted"] > 0]
        attempted_cats.sort(key=lambda x: x[1])
        weakest = [cat for cat, _ in attempted_cats[:3]]
        # If no attempts yet, suggest categories
        if not weakest:
            weakest = ["cpu", "memory", "disk"]

        return {
            "total_incidents": total_incidents,
            "solved_count": solved_count,
            "avg_score": avg_score,
            "total_hints": total_hints,
            "levels": levels_breakdown,
            "recommended_next_level": recommended_level,
            "categories": breakdown,
            "weakest": weakest,
        }
