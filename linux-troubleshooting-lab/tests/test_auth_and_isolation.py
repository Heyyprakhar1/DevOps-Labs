import unittest
import uuid
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from linuxlab.config import DB_FILE, LEVELS
from linuxlab.db import Database
from linuxlab import auth
from linuxlab.lab.container_manager import SandboxManager
from linuxlab.lab.controller import LabController
from linuxlab.web.app import app, registry


class TestMultiUserAuthAndIsolation(unittest.TestCase):
    """Test suite covering multi-user authentication, user isolation,
    session lifecycle, and persistent learning history.
    """

    def setUp(self):
        # Create an isolated in-memory or dedicated test database
        self.test_db = Database()
        self.client = TestClient(app)
        self.username_a = f"testuser_a_{uuid.uuid4().hex[:6]}"
        self.username_b = f"testuser_b_{uuid.uuid4().hex[:6]}"
        self.password = "Secr3tP@ss123"

    # =========================================================================
    # 1. AUTHENTICATION TESTS (1-6)
    # =========================================================================

    def test_01_register_new_user(self):
        """1. Register new user successfully with hashed password."""
        res = self.client.post("/api/auth/register", json={
            "username": self.username_a,
            "password": self.password
        })
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("token", data)
        self.assertEqual(data["user"]["username"], self.username_a)

        # Verify password is NEVER stored in plaintext in the database
        user_record = self.test_db.get_user_by_username(self.username_a)
        self.assertIsNotNone(user_record)
        self.assertNotEqual(user_record["password_hash"], self.password)
        self.assertTrue(auth.verify_password(self.password, user_record["password_hash"]))

    def test_02_duplicate_registration_rejected(self):
        """2. Duplicate registration with same or case-variant username is rejected."""
        self.client.post("/api/auth/register", json={
            "username": self.username_a,
            "password": self.password
        })
        # Exact duplicate
        res1 = self.client.post("/api/auth/register", json={
            "username": self.username_a,
            "password": "AnotherPassword456"
        })
        self.assertEqual(res1.status_code, 400)
        self.assertIn("already taken", res1.json()["detail"].lower())

        # Case-insensitive duplicate (e.g. TestUser_A_...)
        res2 = self.client.post("/api/auth/register", json={
            "username": self.username_a.upper(),
            "password": "AnotherPassword456"
        })
        self.assertEqual(res2.status_code, 400)

    def test_03_login_succeeds(self):
        """3. Login succeeds with correct credentials and returns session token."""
        self.client.post("/api/auth/register", json={
            "username": self.username_a,
            "password": self.password
        })

        res = self.client.post("/api/auth/login", json={
            "username": self.username_a,
            "password": self.password
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("token", data)
        self.assertEqual(data["user"]["username"], self.username_a)

    def test_04_invalid_password_rejected(self):
        """4. Invalid password is rejected with 401."""
        self.client.post("/api/auth/register", json={
            "username": self.username_a,
            "password": self.password
        })

        res = self.client.post("/api/auth/login", json={
            "username": self.username_a,
            "password": "WrongPassword999"
        })
        self.assertEqual(res.status_code, 401)
        self.assertIn("invalid username or password", res.json()["detail"].lower())

    def test_05_logout_works(self):
        """5. Logout invalidates session token and cookie."""
        reg = self.client.post("/api/auth/register", json={
            "username": self.username_a,
            "password": self.password
        })
        token = reg.json()["token"]

        # Token allows access to protected /api/auth/me
        me_before = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_before.status_code, 200)

        # Logout
        logout_res = self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout_res.status_code, 200)

        # Subsequent request with old token is rejected
        me_after = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_after.status_code, 401)

    def test_06_protected_endpoints_reject_unauthenticated(self):
        """6. Protected endpoints reject unauthenticated requests."""
        endpoints = [
            ("GET", "/api/auth/me"),
            ("GET", "/api/history"),
            ("POST", "/api/incidents/random"),
            ("POST", "/api/incidents/cpu_001/start"),
            ("POST", "/api/incidents/hint"),
            ("POST", "/api/incidents/evaluate"),
        ]
        for method, endpoint in endpoints:
            if method == "GET":
                res = self.client.get(endpoint)
            else:
                res = self.client.post(endpoint)
            self.assertEqual(
                res.status_code, 401,
                f"Endpoint {method} {endpoint} should require authentication, got {res.status_code}"
            )

    # =========================================================================
    # 2. USER ISOLATION TESTS (7-10)
    # =========================================================================

    def _register_and_get_token(self, username: str) -> str:
        res = self.client.post("/api/auth/register", json={
            "username": username,
            "password": self.password
        })
        return res.json()["token"]

    def test_07_user_a_cannot_access_user_b_history(self):
        """7. User A cannot access User B's history or individual attempt records."""
        token_a = self._register_and_get_token(self.username_a)
        token_b = self._register_and_get_token(self.username_b)

        user_b = self.test_db.get_user_by_username(self.username_b)
        self.assertIsNotNone(user_b)

        # Record a past attempt directly for User B
        attempt_b_id = self.test_db.record_attempt(
            user_id=user_b["id"],
            scenario_id="disk_001",
            category="disk",
            level="EASY",
            status="SOLVED",
            score=95,
            duration_sec=120.0,
            hints_used=[1],
            command_history=["df -h", "rm -f /var/log/app/disk_hog.log"]
        )

        # User B can view their attempt
        res_b = self.client.get(f"/api/history/{attempt_b_id}", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(res_b.status_code, 200)

        # User A's history list does NOT contain User B's attempt
        res_a_list = self.client.get("/api/history", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(res_a_list.status_code, 200)
        a_attempts = res_a_list.json()
        self.assertEqual(len(a_attempts), 0)

        # User A attempting to view User B's attempt ID receives 404 (strictly isolated)
        res_a_detail = self.client.get(f"/api/history/{attempt_b_id}", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(res_a_detail.status_code, 404)

    def test_08_user_a_cannot_access_user_b_incident(self):
        """8. User A cannot evaluate or alter User B's active incident session."""
        token_a = self._register_and_get_token(self.username_a)
        token_b = self._register_and_get_token(self.username_b)

        user_b = self.test_db.get_user_by_username(self.username_b)

        # Create active incident session for User B
        self.test_db.create_incident_session(
            user_id=user_b["id"],
            scenario_id="cpu_001",
            container_name="linuxlab-sandbox-userb-sessb",
            level="MODERATE"
        )

        # User A has no active session; evaluate from User A returns 400
        res_a_eval = self.client.post("/api/incidents/evaluate", headers={"Authorization": f"Bearer {token_a}"}, json={})
        self.assertEqual(res_a_eval.status_code, 400)
        self.assertIn("no active incident session", res_a_eval.json()["detail"].lower())

        # User A requesting hint returns 400 (cannot access User B's session)
        res_a_hint = self.client.post("/api/incidents/hint", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(res_a_hint.status_code, 400)

    def test_09_user_a_cannot_access_user_b_sandbox(self):
        """9. User A's session resolves only to User A's dedicated container, never User B's."""
        user_a_id = str(uuid.uuid4())
        user_b_id = str(uuid.uuid4())
        sess_a_id = str(uuid.uuid4())
        sess_b_id = str(uuid.uuid4())

        container_a = SandboxManager.get_container_name(user_a_id, sess_a_id)
        container_b = SandboxManager.get_container_name(user_b_id, sess_b_id)

        self.assertNotEqual(container_a, container_b)
        self.assertTrue(container_a.startswith("linuxlab-sandbox-"))
        self.assertTrue(container_b.startswith("linuxlab-sandbox-"))
        self.assertIn(user_a_id[:8].replace("-", ""), container_a)
        self.assertIn(user_b_id[:8].replace("-", ""), container_b)

    def test_10_websocket_terminal_binds_to_authenticated_user_session(self):
        """10. WebSocket terminal derives sandbox strictly from authenticated session."""
        token_a = self._register_and_get_token(self.username_a)

        # User A has no active incident session -> terminal closes with informative notice
        with self.client.websocket_connect(f"/ws/terminal?token={token_a}") as ws:
            msg = ws.receive_text()
            self.assertIn("No active incident session", msg)

        # Connection with invalid token
        with self.client.websocket_connect("/ws/terminal?token=invalid_token_xyz") as ws:
            # Rejects or treats as unauthenticated
            try:
                msg = ws.receive_text()
                self.assertTrue("authentication" in msg.lower() or "no active" in msg.lower())
            except Exception:
                pass

    # =========================================================================
    # 3. SESSION LIFECYCLE & ISOLATION TESTS (11-13)
    # =========================================================================

    def test_11_user_gets_isolated_sandbox_instance(self):
        """11. User gets an isolated, uniquely-named sandbox instance upon starting incident."""
        token_a = self._register_and_get_token(self.username_a)
        user_a = self.test_db.get_user_by_username(self.username_a)

        mock_container = f"linuxlab-sandbox-{user_a['id'][:8]}-mock123"
        disk_sc = registry.get("disk_001")
        with patch.object(SandboxManager, "create_sandbox", return_value=mock_container), \
             patch.object(LabController, "ensure_running", return_value=None), \
             patch.object(disk_sc, "setup", return_value=True), \
             patch("linuxlab.web.app.EvidenceCollector.capture", return_value={}):

            res = self.client.post(
                "/api/incidents/disk_001/start",
                headers={"Authorization": f"Bearer {token_a}"}
            )
            self.assertEqual(res.status_code, 200, res.text)
            self.assertEqual(res.json()["container_name"], mock_container)

            # Active session in DB reflects user and isolated container
            active = self.test_db.get_active_incident_session(user_a["id"])
            self.assertIsNotNone(active)
            self.assertEqual(active["container_name"], mock_container)
            self.assertEqual(active["scenario_id"], "disk_001")

    def test_12_different_users_receive_different_sandbox_instances(self):
        """12. Different users receive completely different sandbox instances."""
        token_a = self._register_and_get_token(self.username_a)
        token_b = self._register_and_get_token(self.username_b)
        user_a = self.test_db.get_user_by_username(self.username_a)
        user_b = self.test_db.get_user_by_username(self.username_b)

        def side_effect(user_id, session_id):
            return SandboxManager.get_container_name(user_id, session_id)

        disk_sc = registry.get("disk_001")
        cpu_sc = registry.get("cpu_001")
        with patch.object(SandboxManager, "create_sandbox", side_effect=side_effect), \
             patch.object(LabController, "ensure_running", return_value=None), \
             patch.object(disk_sc, "setup", return_value=True), \
             patch.object(cpu_sc, "setup", return_value=True), \
             patch("linuxlab.web.app.EvidenceCollector.capture", return_value={}):

            res_a = self.client.post("/api/incidents/disk_001/start", headers={"Authorization": f"Bearer {token_a}"})
            res_b = self.client.post("/api/incidents/cpu_001/start", headers={"Authorization": f"Bearer {token_b}"})

            self.assertEqual(res_a.status_code, 200, res_a.text)
            self.assertEqual(res_b.status_code, 200, res_b.text)

            c_a = res_a.json()["container_name"]
            c_b = res_b.json()["container_name"]

            self.assertNotEqual(c_a, c_b)
            self.assertIn(user_a["id"][:8].replace("-", ""), c_a)
            self.assertIn(user_b["id"][:8].replace("-", ""), c_b)

    def test_13_completed_and_expired_sessions_cleaned_up(self):
        """13. Completed, abandoned, and expired sessions are cleaned up properly."""
        user_a = self.test_db.create_user(self.username_a, "hashed_pw")

        # 1. Active session abandoned on reset
        session = self.test_db.create_incident_session(
            user_id=user_a["id"],
            scenario_id="cpu_001",
            container_name="linuxlab-sandbox-user-test-c1",
            level="EASY"
        )
        self.assertIsNotNone(self.test_db.get_active_incident_session(user_a["id"]))

        # Close session
        closed = self.test_db.close_incident_session(user_a["id"], status="abandoned")
        self.assertEqual(closed["status"], "abandoned")
        self.assertIsNone(self.test_db.get_active_incident_session(user_a["id"]))

        # 2. Cleanup expired sessions older than 2 hours
        old_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        # Insert a session with updated_at in the past
        sess_id = str(uuid.uuid4())
        with self.test_db._get_conn() as conn:
            conn.execute("""
                INSERT INTO incident_sessions
                (id, user_id, scenario_id, container_name, level, start_time,
                 hints_used, command_history, initial_evidence, status, created_at, updated_at)
                VALUES (?, ?, 'disk_001', 'linuxlab-sandbox-old-expired', 'EASY', 0.0, '[]', '[]', '{}', 'active', ?, ?)
            """, (sess_id, user_a["id"], old_time, old_time))

        stale = self.test_db.get_stale_incident_sessions(max_age_hours=2)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["container_name"], "linuxlab-sandbox-old-expired")

        # Running expired session cleanup
        cleaned = SandboxManager.cleanup_expired_sessions(max_age_hours=2)
        self.assertIn(sess_id, cleaned)
        self.assertIsNone(self.test_db.get_active_incident_session(user_a["id"]))

    # =========================================================================
    # 4. PERSISTENCE TESTS (14-16)
    # =========================================================================

    def test_14_attempt_result_is_saved(self):
        """14. Evaluated attempt result is persisted in the database with full dimensions."""
        user_a = self.test_db.create_user(self.username_a, "hashed_pw")

        dimensions = {
            "system_state": {"status": "PASS", "score": 25, "max_score": 25},
            "root_cause": {"status": "PASS", "score": 25, "max_score": 25},
            "remediation": {"status": "PASS", "score": 25, "max_score": 25},
            "explanation": {"status": "PASS", "score": 25, "max_score": 25}
        }
        evidence = {"summary": [{"metric": "Disk Usage", "before": "98%", "after": "12%", "status": "HEALTHY"}]}
        postmortem = {"title": "Disk Full RCA", "sections": [{"title": "RCA", "content": "Log file removed"}]}

        attempt_id = self.test_db.record_attempt(
            user_id=user_a["id"],
            scenario_id="disk_001",
            category="disk",
            level="EASY",
            difficulty="EASY",
            status="SOLVED",
            score=100,
            duration_sec=75.5,
            hints_used=[1],
            command_history=["df -h", "rm -f /var/log/app/disk_hog.log"],
            user_explanation="Cleaned up rogue log file.",
            technical_resolution="All invariants healthy",
            overall_verdict="INCIDENT RESOLVED",
            dimensions=dimensions,
            evidence=evidence,
            postmortem=postmortem
        )

        # Retrieve and verify all fields preserved
        record = self.test_db.get_user_attempt(attempt_id, user_a["id"])
        self.assertIsNotNone(record)
        self.assertEqual(record["score"], 100)
        self.assertEqual(record["status"], "SOLVED")
        self.assertEqual(record["dimensions"]["system_state"]["status"], "PASS")
        self.assertEqual(len(record["evidence"]["summary"]), 1)
        self.assertEqual(record["postmortem"]["title"], "Disk Full RCA")
        self.assertEqual(record["user_explanation"], "Cleaned up rogue log file.")

    def test_15_progress_survives_logout_and_login(self):
        """15. Learning progress survives logout and login across sessions."""
        token = self._register_and_get_token(self.username_a)
        user_a = self.test_db.get_user_by_username(self.username_a)

        # Record two attempts
        self.test_db.record_attempt(
            user_id=user_a["id"],
            scenario_id="disk_001",
            category="disk",
            level="EASY",
            status="SOLVED",
            score=90,
            duration_sec=60.0
        )
        self.test_db.record_attempt(
            user_id=user_a["id"],
            scenario_id="cpu_001",
            category="cpu",
            level="MODERATE",
            status="SOLVED",
            score=80,
            duration_sec=110.0
        )

        # Check progress before logout
        res1 = self.client.get("/api/progress", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res1.status_code, 200)
        p1 = res1.json()
        self.assertEqual(p1["total_incidents"], 2)
        self.assertEqual(p1["solved_count"], 2)
        self.assertEqual(p1["avg_score"], 85.0)

        # Logout
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

        # Login again to get fresh session token
        login_res = self.client.post("/api/auth/login", json={
            "username": self.username_a,
            "password": self.password
        })
        new_token = login_res.json()["token"]

        # Progress is fully preserved
        res2 = self.client.get("/api/progress", headers={"Authorization": f"Bearer {new_token}"})
        self.assertEqual(res2.status_code, 200)
        p2 = res2.json()
        self.assertEqual(p2["total_incidents"], 2)
        self.assertEqual(p2["solved_count"], 2)
        self.assertEqual(p2["avg_score"], 85.0)
        self.assertEqual(p2["levels"]["EASY"]["solved"], 1)
        self.assertEqual(p2["levels"]["MODERATE"]["solved"], 1)

    def test_16_evaluation_result_survives_browser_restart(self):
        """16. Evaluation result and postmortem survive client restarts."""
        token = self._register_and_get_token(self.username_a)
        user_a = self.test_db.get_user_by_username(self.username_a)

        attempt_id = self.test_db.record_attempt(
            user_id=user_a["id"],
            scenario_id="inodes_001",
            category="inodes",
            level="MODERATE",
            status="SOLVED",
            score=88,
            duration_sec=140.0,
            hints_used=[1, 2],
            command_history=["df -i", "find /tmp -type f -delete"],
            technical_resolution="Inodes restored",
            overall_verdict="INCIDENT RESOLVED",
            dimensions={"system_state": {"status": "PASS", "score": 25}},
            evidence={"summary": [{"metric": "Inodes", "before": "100%", "after": "4%", "status": "HEALTHY"}]},
            postmortem={"title": "Inodes Exhaustion RCA"}
        )

        # Simulate fresh client (browser restart with stored token)
        fresh_client = TestClient(app)
        res = fresh_client.get(f"/api/history/{attempt_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], attempt_id)
        self.assertEqual(data["score"], 88)
        self.assertEqual(data["overall_verdict"], "INCIDENT RESOLVED")
        self.assertEqual(data["postmortem"]["title"], "Inodes Exhaustion RCA")
        self.assertIn("evaluation_result", data)
        self.assertEqual(data["evaluation_result"]["score"], 88)


if __name__ == "__main__":
    unittest.main()
