import sqlite3
import json
import uuid
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from linuxlab.config import DB_FILE, LEVELS, CATEGORIES

class Database:
    """Manages persistent SQLite storage for users, authentication sessions,
    isolated incident sessions, and learning attempt history.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new SQLite connection with foreign keys and dict-like row factory."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def init_db(self):
        """Initialize database tables and indexes."""
        with self._get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS incident_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scenario_id TEXT NOT NULL,
                container_name TEXT NOT NULL,
                level TEXT NOT NULL,
                start_time REAL NOT NULL,
                hints_used TEXT NOT NULL DEFAULT '[]',
                command_history TEXT NOT NULL DEFAULT '[]',
                initial_evidence TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS incident_attempts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scenario_id TEXT NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                difficulty TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                score INTEGER NOT NULL,
                duration_sec REAL NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                hints_count INTEGER NOT NULL,
                hints_used TEXT NOT NULL DEFAULT '[]',
                command_history TEXT NOT NULL DEFAULT '[]',
                user_explanation TEXT,
                technical_resolution TEXT,
                overall_verdict TEXT,
                dimensions TEXT NOT NULL DEFAULT '{}',
                evidence TEXT NOT NULL DEFAULT '{}',
                postmortem TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_incident_sessions_user_active ON incident_sessions(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_incident_attempts_user ON incident_attempts(user_id, created_at);
            """)

            # Schema migration: ensure difficulty, started_at, completed_at columns exist
            try:
                cur = conn.execute("PRAGMA table_info(incident_attempts)")
                cols = {row["name"] for row in cur.fetchall()}
                if "difficulty" not in cols and cols:
                    conn.execute("ALTER TABLE incident_attempts ADD COLUMN difficulty TEXT NOT NULL DEFAULT ''")
                if "started_at" not in cols and cols:
                    conn.execute("ALTER TABLE incident_attempts ADD COLUMN started_at TEXT")
                if "completed_at" not in cols and cols:
                    conn.execute("ALTER TABLE incident_attempts ADD COLUMN completed_at TEXT")
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # User Management
    # --------------------------------------------------------------------------

    def create_user(self, username: str, password_hash: str) -> Dict[str, Any]:
        """Insert a new user record. Raises sqlite3.IntegrityError if username exists."""
        user_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, username.strip(), password_hash, created_at)
            )
        return {
            "id": user_id,
            "username": username.strip(),
            "created_at": created_at
        }

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Look up user by case-insensitive username."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Look up user by primary key ID."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    # --------------------------------------------------------------------------
    # Auth Sessions
    # --------------------------------------------------------------------------

    def create_auth_session(self, user_id: str, duration_days: int = 7) -> str:
        """Create a new authenticated token session for user."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=duration_days)).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now.isoformat(), expires_at)
            )
        return token

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate token and return user if token is active and not expired."""
        if not token:
            return None
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT u.id, u.username, u.created_at, s.expires_at, s.token
                FROM auth_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ? AND s.expires_at > ?
            """, (token, now_iso))
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_auth_session(self, token: str) -> bool:
        """Invalidate specific auth session token (logout)."""
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            return cur.rowcount > 0

    def delete_user_sessions(self, user_id: str) -> bool:
        """Invalidate all auth sessions for user."""
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            return cur.rowcount > 0

    # --------------------------------------------------------------------------
    # User-Specific Active Incident Sessions
    # --------------------------------------------------------------------------

    def create_incident_session(
        self,
        user_id: str,
        scenario_id: str,
        container_name: str,
        level: str,
        initial_evidence: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create and persist an active isolated incident session for a user."""
        # First close any previous active session for this user
        self.close_incident_session(user_id, status="abandoned")

        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        ev_json = json.dumps(initial_evidence or {})
        start_time = datetime.now(timezone.utc).timestamp()

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO incident_sessions
                (id, user_id, scenario_id, container_name, level, start_time,
                 hints_used, command_history, initial_evidence, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, 'active', ?, ?)
            """, (session_id, user_id, scenario_id, container_name, level, start_time, ev_json, now, now))

        return self.get_active_incident_session(user_id)  # type: ignore

    def get_active_incident_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve current active incident session for user."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM incident_sessions
                WHERE user_id = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["hints_used"] = json.loads(res.get("hints_used", "[]"))
            res["command_history"] = json.loads(res.get("command_history", "[]"))
            res["initial_evidence"] = json.loads(res.get("initial_evidence", "{}"))
            return res

    def record_hint_to_session(self, user_id: str, hint_level: int) -> bool:
        """Add hint level to active incident session."""
        session = self.get_active_incident_session(user_id)
        if not session:
            return False
        hints = session.get("hints_used", [])
        if hint_level not in hints:
            hints.append(hint_level)
            now = datetime.now(timezone.utc).isoformat()
            with self._get_conn() as conn:
                conn.execute("""
                    UPDATE incident_sessions
                    SET hints_used = ?, updated_at = ?
                    WHERE id = ?
                """, (json.dumps(hints), now, session["id"]))
            return True
        return False

    def record_command_to_session(self, user_id: str, command: str) -> bool:
        """Add executed command line to active incident session."""
        if not command.strip():
            return False
        session = self.get_active_incident_session(user_id)
        if not session:
            return False
        cmds = session.get("command_history", [])
        ts = datetime.now().strftime("%H:%M:%S")
        cmds.append(f"{ts}  {command.strip()}")
        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE incident_sessions
                SET command_history = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(cmds), now, session["id"]))
        return True

    def close_incident_session(self, user_id: str, status: str = "completed") -> Optional[Dict[str, Any]]:
        """Mark active incident session as completed or abandoned and return the record."""
        session = self.get_active_incident_session(user_id)
        if not session:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE incident_sessions
                SET status = ?, updated_at = ?
                WHERE id = ?
            """, (status, now, session["id"]))
        session["status"] = status
        return session

    def get_all_active_containers(self) -> List[str]:
        """Return container names of all currently active sessions across all users."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT container_name FROM incident_sessions WHERE status = 'active'")
            return [row["container_name"] for row in cur.fetchall()]

    def get_stale_incident_sessions(self, max_age_hours: int = 2) -> List[Dict[str, Any]]:
        """Return active sessions older than max_age_hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM incident_sessions
                WHERE status = 'active' AND updated_at < ?
            """, (cutoff,))
            return [dict(r) for r in cur.fetchall()]

    # --------------------------------------------------------------------------
    # Incident Attempts & Persistent User Progress
    # --------------------------------------------------------------------------

    def record_attempt(
        self,
        user_id: str,
        scenario_id: str,
        category: str,
        level: str,
        difficulty: Optional[str] = None,
        status: str = "SOLVED",
        score: int = 100,
        duration_sec: float = 0.0,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        hints_used: Optional[List[int]] = None,
        command_history: Optional[List[str]] = None,
        user_explanation: str = "",
        technical_resolution: str = "",
        overall_verdict: str = "",
        dimensions: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        postmortem: Optional[Dict[str, Any]] = None
    ) -> str:
        """Persist a completed or evaluated incident attempt for user."""
        attempt_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        diff = (difficulty or level).upper()
        comp_at = completed_at or created_at
        if not started_at:
            try:
                dt = datetime.fromisoformat(comp_at.replace("Z", "+00:00"))
                started_at = (dt - timedelta(seconds=duration_sec)).isoformat()
            except Exception:
                started_at = created_at
        hints_list = hints_used or []
        cmds_list = command_history or []

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO incident_attempts
                (id, user_id, scenario_id, category, level, difficulty, status, score, duration_sec,
                 started_at, completed_at, hints_count, hints_used, command_history, user_explanation,
                 technical_resolution, overall_verdict, dimensions, evidence, postmortem, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                attempt_id,
                user_id,
                scenario_id,
                category.lower(),
                level.upper(),
                diff,
                status.upper(),
                score,
                round(duration_sec, 1),
                started_at,
                comp_at,
                len(hints_list),
                json.dumps(hints_list),
                json.dumps(cmds_list),
                user_explanation,
                technical_resolution,
                overall_verdict,
                json.dumps(dimensions or {}),
                json.dumps(evidence or {}),
                json.dumps(postmortem or {}),
                created_at
            ))
        return attempt_id

    def get_user_attempts(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent incident attempts for a specific user."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM incident_attempts
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["hints_used"] = json.loads(item.get("hints_used", "[]"))
                item["command_history"] = json.loads(item.get("command_history", "[]"))
                item["dimensions"] = json.loads(item.get("dimensions", "{}"))
                item["evidence"] = json.loads(item.get("evidence", "{}"))
                item["postmortem"] = json.loads(item.get("postmortem", "{}"))
                item["difficulty"] = item.get("difficulty") or item.get("level", "EASY")
                item["started_at"] = item.get("started_at") or item.get("created_at")
                item["completed_at"] = item.get("completed_at") or item.get("created_at")

                # Attach evaluation result dict
                item["evaluation_result"] = {
                    "score": item["score"],
                    "status": item["status"],
                    "overall_verdict": item["overall_verdict"],
                    "technical_resolution": item["technical_resolution"],
                    "dimensions": item["dimensions"],
                    "evidence": item["evidence"],
                    "postmortem": item["postmortem"],
                    "user_explanation": item["user_explanation"],
                }

                # Human-friendly scenario title
                from linuxlab.scenarios.registry import registry
                sc = registry.get(item["scenario_id"])
                item["scenario_title"] = sc.title if sc else item["scenario_id"]

                results.append(item)
            return results

    def get_user_attempt(self, attempt_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific attempt ensuring user authorization."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM incident_attempts
                WHERE id = ? AND user_id = ?
            """, (attempt_id, user_id))
            row = cur.fetchone()
            if not row:
                return None
            item = dict(row)
            item["hints_used"] = json.loads(item.get("hints_used", "[]"))
            item["command_history"] = json.loads(item.get("command_history", "[]"))
            item["dimensions"] = json.loads(item.get("dimensions", "{}"))
            item["evidence"] = json.loads(item.get("evidence", "{}"))
            item["postmortem"] = json.loads(item.get("postmortem", "{}"))
            item["difficulty"] = item.get("difficulty") or item.get("level", "EASY")
            item["started_at"] = item.get("started_at") or item.get("created_at")
            item["completed_at"] = item.get("completed_at") or item.get("created_at")

            item["evaluation_result"] = {
                "score": item["score"],
                "status": item["status"],
                "overall_verdict": item["overall_verdict"],
                "technical_resolution": item["technical_resolution"],
                "dimensions": item["dimensions"],
                "evidence": item["evidence"],
                "postmortem": item["postmortem"],
                "user_explanation": item["user_explanation"],
            }

            from linuxlab.scenarios.registry import registry
            sc = registry.get(item["scenario_id"])
            item["scenario_title"] = sc.title if sc else item["scenario_id"]
            return item

    def calculate_user_progress(self, user_id: str) -> Dict[str, Any]:
        """Aggregate progress metrics for a specific user."""
        user = self.get_user_by_id(user_id)
        username = user["username"] if user else ""

        attempts = self.get_user_attempts(user_id, limit=500)
        total_attempts = len(attempts)
        solved_count = sum(1 for a in attempts if a.get("status") == "SOLVED")
        total_score = sum(a.get("score", 0) for a in attempts)
        avg_score = round(total_score / total_attempts, 1) if total_attempts > 0 else 0
        hints_used = sum(a.get("hints_count", 0) for a in attempts)
        resolution_rate = round((solved_count / total_attempts) * 100) if total_attempts > 0 else 0

        # Level Mastery Breakdown
        level_stats: Dict[str, Dict[str, Any]] = {
            lvl: {"attempted": 0, "solved": 0, "total_score": 0} for lvl in LEVELS
        }
        for a in attempts:
            lvl = a.get("level", "EASY").upper()
            if lvl not in level_stats:
                lvl = "EASY"
            level_stats[lvl]["attempted"] += 1
            if a.get("status") == "SOLVED":
                level_stats[lvl]["solved"] += 1
            level_stats[lvl]["total_score"] += a.get("score", 0)

        levels_breakdown = {}
        for lvl in LEVELS:
            data = level_stats[lvl]
            att = data["attempted"]
            sol = data["solved"]
            score_avg = round(data["total_score"] / att, 1) if att > 0 else 0
            rate = round((sol / att) * 100) if att > 0 else 0
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

        # Category Breakdown
        cat_stats: Dict[str, Dict[str, Any]] = {
            cat: {"attempted": 0, "solved": 0, "total_score": 0} for cat in CATEGORIES
        }
        for a in attempts:
            c = a.get("category", "").lower()
            if c in cat_stats:
                cat_stats[c]["attempted"] += 1
                if a.get("status") == "SOLVED":
                    cat_stats[c]["solved"] += 1
                cat_stats[c]["total_score"] += a.get("score", 0)

        categories_breakdown = {}
        for c, data in cat_stats.items():
            att = data["attempted"]
            sol = data["solved"]
            categories_breakdown[c] = {
                "attempted": att,
                "solved": sol,
                "success_rate": round((sol / att) * 100) if att > 0 else 0,
                "avg_score": round(data["total_score"] / att, 1) if att > 0 else 0,
            }

        # Recommended Practice Level
        recommended_level = "EASY"
        for lvl in LEVELS:
            br = levels_breakdown[lvl]
            if br["solved"] < 4:
                recommended_level = lvl
                break

        # Weak Areas
        weak_areas = []
        for c, stats in categories_breakdown.items():
            if stats["attempted"] >= 2 and stats["success_rate"] < 60:
                weak_areas.append(f"{c.upper()} ({stats['success_rate']}% pass rate)")

        return {
            "username": username,
            "overall_score": avg_score,
            "total_incidents": total_attempts,
            "solved_count": solved_count,
            "avg_score": avg_score,
            "hints_used": hints_used,
            "resolution_rate": resolution_rate,
            "recommended_level": recommended_level,
            "weak_areas": weak_areas,
            "levels": levels_breakdown,
            "categories": categories_breakdown,
            "recent_attempts": attempts[:10],
        }

# Global database instance
db = Database()
