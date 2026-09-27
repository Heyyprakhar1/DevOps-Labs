from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any
from linuxlab.lab.controller import LabController

class Scenario(ABC):
    """Abstract base class for all Linux troubleshooting scenarios."""

    id: str
    category: str
    difficulty: str = "EASY"
    level: str = "EASY"
    title: str
    symptoms: List[str]
    context: str
    objective: str
    hints: List[str]
    expected_root_cause: str
    expected_fix: str
    learning_points: List[str]

    # Extended attributes for progressive learning
    expected_tools: List[str] = []
    investigation_guidance: str = ""
    validation: str = ""
    postmortem_sections: Dict[str, Any] = {}
    interview_takeaways: List[str] = []

    def __init__(self):
        if not hasattr(self, "hints") or len(self.hints) < 3:
            raise ValueError(f"Scenario {self.id} must define at least 3 progressive hints.")
        # Ensure level and difficulty are aligned
        if hasattr(self, "level") and not hasattr(self, "difficulty"):
            self.difficulty = self.level
        elif hasattr(self, "difficulty") and not hasattr(self, "level"):
            self.level = self.difficulty

    @property
    def root_cause(self) -> str:
        return getattr(self, "expected_root_cause", "")

    @property
    def remediation(self) -> str:
        return getattr(self, "expected_fix", "")

    @property
    def explanation(self) -> List[str]:
        return getattr(self, "learning_points", [])

    @abstractmethod
    def setup(self, controller: LabController) -> bool:
        """Inject the fault / incident condition into the lab container."""
        pass

    @abstractmethod
    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verify the actual state of the lab container.
        Returns:
            (is_solved: bool, feedback_message: str, metric_details: dict)
        """
        pass

    def get_briefing(self, include_guidance: bool = False) -> Dict[str, Any]:
        """Return safe user-facing incident briefing without revealing root cause or fix."""
        lvl = getattr(self, "level", getattr(self, "difficulty", "EASY"))
        briefing = {
            "id": self.id,
            "category": self.category.upper(),
            "difficulty": getattr(self, "difficulty", lvl),
            "level": lvl,
            "title": self.title,
            "symptoms": self.symptoms,
            "context": self.context,
            "objective": self.objective,
        }
        if include_guidance:
            briefing["investigation_guidance"] = getattr(self, "investigation_guidance", "")
            briefing["expected_tools"] = getattr(self, "expected_tools", [])
        return briefing
