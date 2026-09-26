import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

from linuxlab.config import LEVELS
from linuxlab.scenarios.registry import registry
from linuxlab.evaluation.dimensional import DimensionalEvaluator
from linuxlab.evaluation.evidence import EvidenceCollector
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.evaluation.evaluator import IncidentEvaluator
from linuxlab.state.manager import StateManager
from linuxlab.lab.controller import LabController


class TestStateBasedEvaluation(unittest.TestCase):
    """Test suite for state-based incident evaluation and the 4-dimensional assessment system."""

    def setUp(self):
        self.scenario = registry.get("disk_001")
        self.assertIsNotNone(self.scenario)

    def test_correct_fix_good_explanation(self):
        """Test 1: Correct fix + thorough explanation -> PASS across all dimensions."""
        user_explanation = (
            "Diagnosed high disk usage on /var/log with df -h and du -sh. "
            "Found /var/log/app/transaction.log was consuming excessive space due to runaway debug logging. "
            "Truncated the log file using '> /var/log/app/transaction.log' and verified free disk space."
        )
        commands = [
            "df -h",
            "du -sh /var/log/*",
            "> /var/log/app/transaction.log",
            "df -h"
        ]

        # Machine verification confirms solved state
        eval_result = DimensionalEvaluator.evaluate(
            scenario=self.scenario,
            is_solved=True,
            feedback_msg="transaction.log is truncated and disk is healthy",
            user_explanation=user_explanation,
            command_history=commands,
            level="EASY"
        )

        dims = eval_result["dimensions"]
        self.assertEqual(dims["system_state"]["status"], "PASS")
        self.assertEqual(dims["remediation"]["status"], "PASS")
        self.assertEqual(dims["root_cause"]["status"], "PASS")
        self.assertEqual(dims["explanation"]["status"], "PASS")
        self.assertEqual(eval_result["overall_verdict"], "INCIDENT RESOLVED")
        self.assertEqual(eval_result["technical_resolution"], "PASS")

    def test_correct_fix_poor_explanation_edge_case(self):
        """Test 2: Critical Edge Case: Correct fix + poor/symptom-only explanation.
        Example: 'I fixed the disk issue.'
        Expected:
          - System State: PASS
          - Remediation: PASS
          - Root Cause: PARTIAL or UNKNOWN
          - Explanation: NEEDS IMPROVEMENT
          - Overall Verdict: INCIDENT RESOLVED (UI must NOT say incident failed)
        """
        user_explanation = "I fixed the disk issue."
        commands = [
            "df -h",
            "> /var/log/app/transaction.log"
        ]

        eval_result = DimensionalEvaluator.evaluate(
            scenario=self.scenario,
            is_solved=True,
            feedback_msg="transaction.log is truncated and disk is healthy",
            user_explanation=user_explanation,
            command_history=commands,
            level="EASY"
        )

        dims = eval_result["dimensions"]
        self.assertEqual(dims["system_state"]["status"], "PASS")
        self.assertEqual(dims["remediation"]["status"], "PASS")
        self.assertIn(dims["root_cause"]["status"], ["PARTIAL", "UNKNOWN", "PARTIAL/UNKNOWN"])
        self.assertEqual(dims["explanation"]["status"], "NEEDS IMPROVEMENT")
        self.assertEqual(eval_result["overall_verdict"], "INCIDENT RESOLVED")
        self.assertEqual(eval_result["technical_resolution"], "PASS")
        self.assertIn(
            "Your system is in the expected healthy state, but your explanation does not demonstrate the troubleshooting reasoning clearly.",
            eval_result["explanation_feedback"]
        )

    def test_incorrect_fix(self):
        """Test 3: Incorrect fix -> Technical State: FAIL, Overall: INCIDENT UNRESOLVED."""
        user_explanation = "I rebooted the machine and checked logs."
        commands = [
            "uptime",
            "dmesg"
        ]

        eval_result = DimensionalEvaluator.evaluate(
            scenario=self.scenario,
            is_solved=False,
            feedback_msg="transaction.log still exceeds threshold (350MB)",
            user_explanation=user_explanation,
            command_history=commands,
            level="EASY"
        )

        dims = eval_result["dimensions"]
        self.assertEqual(dims["system_state"]["status"], "FAIL")
        self.assertEqual(dims["remediation"]["status"], "FAIL")
        self.assertEqual(eval_result["overall_verdict"], "INCIDENT UNRESOLVED")
        self.assertEqual(eval_result["technical_resolution"], "FAIL")

    def test_unrelated_change(self):
        """Test 4: Unrelated change -> Technical State: FAIL, Remediation: FAIL."""
        user_explanation = "I created a temporary swap file in /tmp to free memory."
        commands = [
            "touch /tmp/dummy_swap",
            "chmod 600 /tmp/dummy_swap"
        ]

        eval_result = DimensionalEvaluator.evaluate(
            scenario=self.scenario,
            is_solved=False,
            feedback_msg="Filesystem still full; /var/log/app/transaction.log untouched",
            user_explanation=user_explanation,
            command_history=commands,
            level="MODERATE"
        )

        dims = eval_result["dimensions"]
        self.assertEqual(dims["system_state"]["status"], "FAIL")
        self.assertEqual(dims["remediation"]["status"], "FAIL")
        self.assertEqual(eval_result["overall_verdict"], "INCIDENT UNRESOLVED")
        self.assertEqual(eval_result["technical_resolution"], "FAIL")

    @unittest.mock.patch.object(StateManager, "record_history_entry")
    @unittest.mock.patch.object(StateManager, "clear_session")
    def test_dimensional_evaluation_response_fields(self, mock_clear, mock_record):
        """Test 5: Dimensional evaluation response fields exist with correct types and keys."""
        session = {
            "scenario_id": "disk_001",
            "start_time": 1000.0,
            "hints_used": [],
            "command_history": ["df -h", "> /var/log/app/transaction.log"]
        }

        # Mock the controller so verify passes
        mock_controller = MagicMock()
        mock_controller.exec_cmd.return_value = (0, "healthy", "")

        # Use mock scenario verify
        scenario_mock = MagicMock()
        scenario_mock.id = "disk_001"
        scenario_mock.category = "disk"
        scenario_mock.level = "EASY"
        scenario_mock.verify.return_value = (True, "Disk capacity restored", None)
        scenario_mock.expected_root_cause = "Runaway logging"
        scenario_mock.expected_fix = "Truncate transaction.log"
        scenario_mock.learning_points = ["Rotate logs"]

        evaluator = IncidentEvaluator(controller=mock_controller)

        report = evaluator.evaluate_session(
            session=session,
            scenario=scenario_mock,
            user_explanation="I fixed the disk issue."
        )

        self.assertIn("overall_verdict", report)
        self.assertIn("is_solved", report)
        self.assertIn("dimensions", report)
        self.assertIn("evidence", report)
        self.assertIn("score", report)
        self.assertIn("breakdown", report)
        self.assertIn("explanation_feedback", report)

        dims = report["dimensions"]
        for key in ["system_state", "root_cause", "remediation", "explanation"]:
            self.assertIn(key, dims)
            self.assertIn("name", dims[key])
            self.assertIn("status", dims[key])
            self.assertIn("detail", dims[key])

    def test_evidence_comparison_generation(self):
        """Test 6: Before/after evidence generated correctly with metric comparison."""
        before_snapshot = {
            "system": {
                "cpu_percent": "95.0%",
                "mem_formatted": "3800MB used",
                "disk_percent": "98%",
                "web_app_status": "healthy",
                "payment_api_status": "healthy"
            },
            "scenario": {
                "transaction_log_size_mb": 350
            }
        }
        after_snapshot = {
            "system": {
                "cpu_percent": "12.0%",
                "mem_formatted": "1800MB used",
                "disk_percent": "42%",
                "web_app_status": "healthy",
                "payment_api_status": "healthy"
            },
            "scenario": {
                "transaction_log_size_mb": 0
            }
        }

        comparison = EvidenceCollector.compare(
            before=before_snapshot,
            after=after_snapshot,
            scenario=self.scenario,
            is_solved=True
        )

        self.assertIn("summary", comparison)
        summary = comparison["summary"]
        self.assertTrue(len(summary) >= 3)

        # Check that the metric comparison contains expected keys
        log_metric = next((m for m in summary if "transaction.log" in m["metric"]), None)
        self.assertIsNotNone(log_metric)
        self.assertEqual(log_metric["status"], "PASS")
        self.assertIn("350", log_metric["before"])
        self.assertIn("0", log_metric["after"])

    def test_scoring_preserves_legacy_fields_and_adds_dimensional(self):
        """Test 7: Score calculation preserves legacy fields and adds dimensional breakdown."""
        result = IncidentScorer.calculate(
            is_solved=True,
            hints_used=[1],
            duration_sec=120,
            level="EASY",
            command_count=5,
            user_explanation="Identified disk full and truncated transaction.log",
            scenario=self.scenario
        )

        # Legacy fields MUST exist
        self.assertIn("score", result)
        self.assertIn("base", result)
        self.assertIn("hint_deduction", result)
        self.assertIn("command_penalty", result)
        self.assertIn("reasoning_bonus", result)

        # Dimensional breakdown MUST exist
        self.assertIn("dimensional_breakdown", result)
        breakdown = result["dimensional_breakdown"]
        self.assertIn("technical", breakdown)
        self.assertIn("diagnosis", breakdown)
        self.assertIn("explanation", breakdown)
        self.assertIn("score", breakdown["technical"])
        self.assertIn("max", breakdown["technical"])

        # Score must be bounded between 0 and 100
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


class TestLiveSandboxEvaluation(unittest.TestCase):
    """Live container validation testing real state inspection and the edge case."""

    @classmethod
    def setUpClass(cls):
        cls.ctrl = LabController()
        cls.ctrl.ensure_running()
        cls.ctrl.reset()

    def setUp(self):
        self.ctrl.reset()

    def tearDown(self):
        self.ctrl.reset()

    def test_live_disk_incident_edge_case(self):
        """Live test: Fix disk incident in real container, submit poor explanation.
        Verify System State PASS and Explanation NEEDS IMPROVEMENT in real evaluator.
        """
        s = registry.get("disk_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))

        # Capture initial evidence
        initial_ev = EvidenceCollector.capture(self.ctrl, s)

        # Verify broken state initially
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)

        # User performs fix in sandbox
        self.ctrl.exec_cmd("> /var/log/app/transaction.log")

        # Create session dict
        session = {
            "scenario_id": "disk_001",
            "start_time": 1000.0,
            "hints_used": [],
            "command_history": ["df -h", "> /var/log/app/transaction.log"],
            "initial_evidence": initial_ev
        }

        evaluator = IncidentEvaluator(controller=self.ctrl)
        result = evaluator.evaluate_session(
            session=session,
            scenario=s,
            user_explanation="I fixed the disk issue."
        )

        self.assertTrue(result["is_solved"])
        self.assertEqual(result["overall_verdict"], "INCIDENT RESOLVED")
        self.assertEqual(result["dimensions"]["system_state"]["status"], "PASS")
        self.assertEqual(result["dimensions"]["remediation"]["status"], "PASS")
        self.assertEqual(result["dimensions"]["explanation"]["status"], "NEEDS IMPROVEMENT")
        self.assertIn("Your system is in the expected healthy state", result["explanation_feedback"])
        self.assertTrue(len(result["evidence"]["summary"]) > 0)


if __name__ == "__main__":
    unittest.main()
