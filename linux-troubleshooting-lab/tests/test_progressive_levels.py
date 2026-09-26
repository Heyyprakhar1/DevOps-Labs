import unittest
from linuxlab.config import LEVELS, LEVEL_DESCRIPTIONS
from linuxlab.scenarios.registry import registry
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.evaluation.reports import IncidentReportGenerator
from linuxlab.state.manager import StateManager
from linuxlab.interview.questions import get_interview_scenarios_for_level

class TestProgressiveLevels(unittest.TestCase):
    """Automated unit test suite verifying the 5-level progressive learning system."""

    def test_level_definitions(self):
        """Verify the 5 progressive levels and their descriptions."""
        self.assertEqual(LEVELS, ["EASY", "MODERATE", "FLUENT", "ADVANCED", "EXPERT"])
        for lvl in LEVELS:
            self.assertIn(lvl, LEVEL_DESCRIPTIONS)
            self.assertTrue(len(LEVEL_DESCRIPTIONS[lvl]) > 10)

    def test_scenario_counts_per_level(self):
        """Verify exactly 5 scenarios per level (25 scenarios total)."""
        all_scenarios = registry.list_all()
        self.assertEqual(len(all_scenarios), 25, f"Expected 25 total scenarios, found {len(all_scenarios)}")

        for lvl in LEVELS:
            filtered = registry.filter(level=lvl)
            self.assertEqual(len(filtered), 5, f"Expected 5 scenarios for {lvl}, got {len(filtered)}: {[s.id for s in filtered]}")

    def test_level_scoring_rules(self):
        """Verify level-aware scoring, command efficiency penalties, and reasoning bonuses."""
        # Easy: no command penalties, 100 points
        easy = IncidentScorer.calculate(is_solved=True, hints_used=[], duration_sec=60, level="EASY", command_count=10)
        self.assertEqual(easy["score"], 100)
        self.assertEqual(easy["command_penalty"], 0)

        # Expert: command count > 40 incurs a 5-point penalty
        expert = IncidentScorer.calculate(
            is_solved=True,
            hints_used=[1],
            duration_sec=300,
            level="EXPERT",
            command_count=55,
            user_explanation="Identified socket leak due to missing SO_REUSEADDR and worker hung"
        )
        self.assertEqual(expert["hint_deduction"], 5)
        self.assertEqual(expert["command_penalty"], 5)
        self.assertGreaterEqual(expert["reasoning_bonus"], 5)
        self.assertEqual(expert["score"], 95)  # 100 - 5 (hint) - 5 (cmds) + 5 (reasoning)

        # Unsolved scenario score is always 0
        unsolved = IncidentScorer.calculate(is_solved=False, hints_used=[], duration_sec=60, level="EXPERT")
        self.assertEqual(unsolved["score"], 0)

    def test_structured_postmortems_by_level(self):
        """Verify postmortem generator produces level-adapted structures."""
        # EASY -> Beginner Postmortem (4 sections)
        easy_sc = registry.filter(level="EASY")[0]
        easy_pm = IncidentReportGenerator.get_structured_sections(easy_sc)
        self.assertEqual(easy_pm["level"], "EASY")
        self.assertIn("What Happened", easy_pm["sections"])
        self.assertIn("Commands Used", easy_pm["sections"])
        self.assertIn("What Output Meant", easy_pm["sections"])
        self.assertIn("Why Fix Worked", easy_pm["sections"])

        # MODERATE -> Junior Transition Postmortem (5 sections)
        mod_sc = registry.filter(level="MODERATE")[0]
        mod_pm = IncidentReportGenerator.get_structured_sections(mod_sc)
        self.assertEqual(mod_pm["level"], "MODERATE")
        self.assertIn("Investigation Sequence", mod_pm["sections"])
        self.assertIn("Evidence Collected", mod_pm["sections"])

        # FLUENT -> DevOps Postmortem (4 sections)
        fluent_sc = registry.filter(level="FLUENT")[0]
        fluent_pm = IncidentReportGenerator.get_structured_sections(fluent_sc)
        self.assertEqual(fluent_pm["level"], "FLUENT")
        self.assertIn("Troubleshooting Methodology", fluent_pm["sections"])
        self.assertIn("Why Alternative Causes Were Ruled Out", fluent_pm["sections"])

        # ADVANCED -> Cross-layer Postmortem (5 sections)
        adv_sc = registry.filter(level="ADVANCED")[0]
        adv_pm = IncidentReportGenerator.get_structured_sections(adv_sc)
        self.assertEqual(adv_pm["level"], "ADVANCED")
        self.assertIn("Signal Correlation Across Layers", adv_pm["sections"])
        self.assertIn("Elimination of Hypotheses", adv_pm["sections"])

        # EXPERT -> 10-Point SRE Postmortem
        expert_sc = registry.filter(level="EXPERT")[0]
        expert_pm = IncidentReportGenerator.get_structured_sections(expert_sc)
        self.assertEqual(expert_pm["level"], "EXPERT")
        self.assertEqual(len(expert_pm["sections"]), 10)
        self.assertIn("1. Incident Summary", expert_pm["sections"])
        self.assertIn("10. Prevention / Follow-up Actions", expert_pm["sections"])

    def test_interview_questions_by_level(self):
        """Verify interview question bank filters by difficulty level."""
        for lvl in LEVELS:
            qs = get_interview_scenarios_for_level(lvl)
            self.assertTrue(len(qs) >= 1, f"Expected at least 1 interview scenario for {lvl}")
            for q in qs:
                self.assertEqual(q.get("level", "FLUENT"), lvl)

    def test_progress_level_mastery(self):
        """Verify state manager computes level mastery metrics and next recommendation."""
        prog = StateManager.calculate_progress()
        self.assertIn("levels", prog)
        self.assertIn("recommended_next_level", prog)
        for lvl in LEVELS:
            self.assertIn(lvl, prog["levels"])
            lvl_stat = prog["levels"][lvl]
            self.assertIn("attempted", lvl_stat)
            self.assertIn("solved", lvl_stat)
            self.assertIn("rate", lvl_stat)
            self.assertIn("bar", lvl_stat)

if __name__ == "__main__":
    unittest.main()
