import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

from linuxlab.config import DB_FILE
from linuxlab.db import Database
from linuxlab.scenarios.registry import registry
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.web.app import app


class TestOptInTroubleshootingHints(unittest.TestCase):
    """Test suite verifying opt-in progressive hints, removal of always-visible
    investigation guidance and recommended tools, and preservation of existing scoring.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = Database()
        cls.static_dir = Path(__file__).resolve().parent.parent / "linuxlab" / "web" / "static"
        cls.index_html_path = cls.static_dir / "index.html"

    def setUp(self):
        self.username = f"hint_test_{uuid.uuid4().hex[:6]}"
        self.password = "P@ssword1234!"
        reg = self.client.post("/api/auth/register", json={
            "username": self.username,
            "password": self.password,
        })
        self.assertEqual(reg.status_code, 200)
        self.token = reg.json()["token"]
        self.user = reg.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _create_active_session(self, scenario_id="disk_001", level="EASY"):
        return self.db.create_incident_session(
            user_id=self.user["id"],
            scenario_id=scenario_id,
            container_name=f"test-sandbox-{uuid.uuid4().hex[:6]}",
            level=level,
            initial_evidence={"status": "initial"}
        )

    def test_01_incident_page_does_not_expose_investigation_guidance_by_default(self):
        """1. Incident page does NOT expose investigation guidance by default."""
        # Check static HTML template
        html_content = self.index_html_path.read_text(encoding="utf-8")
        self.assertNotIn("Investigation Guidance", html_content,
                         "Investigation Guidance title should not be in incident sidebar HTML.")
        self.assertNotIn("incident-guidance", html_content,
                         "incident-guidance element should be removed from incident sidebar HTML.")

        # Check API status with active incident
        self._create_active_session("disk_001")
        res = self.client.get("/api/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        incident = data.get("active_incident")
        self.assertIsNotNone(incident)
        self.assertNotIn("investigation_guidance", incident,
                         "active_incident API should not expose investigation_guidance by default.")

        # Check scenario briefing
        sc = registry.get("disk_001")
        briefing = sc.get_briefing()
        self.assertNotIn("investigation_guidance", briefing,
                         "get_briefing() must not expose investigation_guidance by default.")

    def test_02_recommended_tools_are_not_visible_by_default(self):
        """2. Recommended tools are NOT visible by default."""
        # Check static HTML template
        html_content = self.index_html_path.read_text(encoding="utf-8")
        self.assertNotIn("Recommended Tools", html_content,
                         "Recommended Tools section should not be in incident sidebar HTML.")
        self.assertNotIn("incident-tools", html_content,
                         "incident-tools element should be removed from incident sidebar HTML.")

        # Check API status with active incident
        self._create_active_session("disk_001")
        res = self.client.get("/api/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        incident = data.get("active_incident")
        self.assertIsNotNone(incident)
        self.assertNotIn("expected_tools", incident,
                         "active_incident API should not expose expected_tools by default.")

        # Check scenario briefing
        sc = registry.get("disk_001")
        briefing = sc.get_briefing()
        self.assertNotIn("expected_tools", briefing,
                         "get_briefing() must not expose expected_tools by default.")

    def test_03_show_approach_hint_is_available(self):
        """3. 'Show Approach Hint' is available in the UI help box."""
        html_content = self.index_html_path.read_text(encoding="utf-8")
        self.assertIn("💡 NEED HELP?", html_content)
        self.assertIn("Show Approach Hint", html_content)
        self.assertIn("btn-request-hint", html_content)
        self.assertIn("help-hint-counter", html_content)
        self.assertIn("revealed-hints-list", html_content)

    def test_04_first_hint_can_be_requested(self):
        """4. First hint can be requested and returns direction."""
        self._create_active_session("disk_001")

        # Request first hint
        res = self.client.post("/api/incidents/hint", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["exhausted"])
        self.assertEqual(data["level"], 1)
        self.assertEqual(data["penalty"], 5)
        self.assertIn("First determine what resource is actually exhausted", data["hint"])
        self.assertEqual(data["hints_used"], [1])

    def test_05_first_hint_does_not_reveal_all_later_hints(self):
        """5. First hint does not reveal all later hints."""
        self._create_active_session("disk_001")

        # Request first hint
        res1 = self.client.post("/api/incidents/hint", headers=self.headers)
        self.assertEqual(res1.status_code, 200)

        # Check active incident status
        st_res = self.client.get("/api/status", headers=self.headers)
        self.assertEqual(st_res.status_code, 200)
        incident = st_res.json()["active_incident"]

        self.assertEqual(incident["hints_used"], [1])
        unlocked = incident["unlocked_hints"]
        self.assertEqual(len(unlocked), 1)
        self.assertEqual(unlocked[0]["level"], 1)

        # Verify hint 2 and hint 3 text are not yet revealed
        sc = registry.get("disk_001")
        self.assertNotIn(sc.hints[1], [h["hint"] for h in unlocked])
        self.assertNotIn(sc.hints[2], [h["hint"] for h in unlocked])

    def test_06_second_hint_reveals_more_guidance(self):
        """6. Second hint reveals more guidance without revealing third hint."""
        self._create_active_session("disk_001")

        # Unlock Hint 1
        self.client.post("/api/incidents/hint", headers=self.headers)

        # Unlock Hint 2
        res2 = self.client.post("/api/incidents/hint", headers=self.headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["level"], 2)
        self.assertEqual(data2["penalty"], 10)
        self.assertEqual(data2["hints_used"], [1, 2])

        # Check status
        st_res = self.client.get("/api/status", headers=self.headers)
        incident = st_res.json()["active_incident"]
        self.assertEqual(len(incident["unlocked_hints"]), 2)
        self.assertEqual([h["level"] for h in incident["unlocked_hints"]], [1, 2])

        # Verify hint 3 is still hidden
        sc = registry.get("disk_001")
        self.assertNotIn(sc.hints[2], [h["hint"] for h in incident["unlocked_hints"]])

    def test_07_third_hint_reveals_strongest_available_guidance(self):
        """7. Third hint reveals the strongest available guidance, then exhausts."""
        self._create_active_session("disk_001")

        # Unlock Hint 1, 2, 3
        self.client.post("/api/incidents/hint", headers=self.headers)
        self.client.post("/api/incidents/hint", headers=self.headers)
        res3 = self.client.post("/api/incidents/hint", headers=self.headers)
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        self.assertEqual(data3["level"], 3)
        self.assertEqual(data3["penalty"], 15)
        self.assertIn("transaction.log", data3["hint"])
        self.assertEqual(data3["hints_used"], [1, 2, 3])

        # Subsequent hint request reports exhausted
        res4 = self.client.post("/api/incidents/hint", headers=self.headers)
        self.assertEqual(res4.status_code, 200)
        self.assertTrue(res4.json()["exhausted"])

    def test_08_hint_counter_updates_correctly(self):
        """8. Hint counter updates correctly from 0/3 -> 1/3 -> 2/3 -> 3/3."""
        self._create_active_session("disk_001")

        # Initial: 0/3
        st0 = self.client.get("/api/status", headers=self.headers).json()["active_incident"]
        self.assertEqual(len(st0["hints_used"]), 0)

        # After 1st hint: 1/3
        self.client.post("/api/incidents/hint", headers=self.headers)
        st1 = self.client.get("/api/status", headers=self.headers).json()["active_incident"]
        self.assertEqual(len(st1["hints_used"]), 1)

        # After 2nd hint: 2/3
        self.client.post("/api/incidents/hint", headers=self.headers)
        st2 = self.client.get("/api/status", headers=self.headers).json()["active_incident"]
        self.assertEqual(len(st2["hints_used"]), 2)

        # After 3rd hint: 3/3
        self.client.post("/api/incidents/hint", headers=self.headers)
        st3 = self.client.get("/api/status", headers=self.headers).json()["active_incident"]
        self.assertEqual(len(st3["hints_used"]), 3)

    def test_09_existing_hint_penalties_remain_intact(self):
        """9. Existing hint penalties remain intact in scoring calculations."""
        # 0 hints used -> 0 penalty
        s0 = IncidentScorer.calculate(is_solved=True, hints_used=[], duration_sec=60, level="EASY")
        self.assertEqual(s0["hint_deduction"], 0)

        # 1 hint used -> 5 penalty
        s1 = IncidentScorer.calculate(is_solved=True, hints_used=[1], duration_sec=60, level="EASY")
        self.assertEqual(s1["hint_deduction"], 5)

        # 2 hints used -> 15 penalty (5 + 10)
        s2 = IncidentScorer.calculate(is_solved=True, hints_used=[1, 2], duration_sec=60, level="EASY")
        self.assertEqual(s2["hint_deduction"], 15)

        # 3 hints used -> 30 penalty (5 + 10 + 15)
        s3 = IncidentScorer.calculate(is_solved=True, hints_used=[1, 2, 3], duration_sec=60, level="EASY")
        self.assertEqual(s3["hint_deduction"], 30)

    def test_10_disk_scenario_hint_progression(self):
        """10. Verify disk scenario progressive hint structure: Direction -> Investigation -> Strong clue."""
        sc = registry.get("disk_001")
        self.assertGreaterEqual(len(sc.hints), 3)

        # Hint 1 is directional without giving away exact files or commands
        self.assertEqual(sc.hints[0], "First determine what resource is actually exhausted.")
        # Hint 2 directs investigation
        self.assertIn("narrow the investigation to the directories consuming the most space", sc.hints[1])
        # Hint 3 provides strong clue and targeted remediation
        self.assertIn("transaction.log", sc.hints[2])


if __name__ == "__main__":
    unittest.main()
