import subprocess
import time
import logging
from typing import Optional, List
from linuxlab.config import IMAGE_NAME, CONTAINER_NAME
from linuxlab.lab.controller import LabController
from linuxlab.db import db

logger = logging.getLogger("linuxlab.container_manager")

class SandboxManager:
    """Manages the creation, lifecycle, resource limits, and cleanup of isolated user sandboxes."""

    NETWORK_NAME = "linux-troubleshooting-lab_default"

    @classmethod
    def get_container_name(cls, user_id: str, session_id: str) -> str:
        """Derive deterministic unique container name for user session."""
        u_prefix = user_id.replace("-", "")[:8]
        s_prefix = session_id.replace("-", "")[:8]
        return f"linuxlab-sandbox-{u_prefix}-{s_prefix}"

    @classmethod
    def create_sandbox(cls, user_id: str, session_id: str) -> str:
        """Create and start an isolated Docker container with strict resource limits."""
        container_name = cls.get_container_name(user_id, session_id)

        # 1. Clean up any previous container for this user first
        cls.cleanup_user_sandboxes(user_id)

        # 2. Check if this exact container name exists and remove it
        cls.destroy_sandbox(container_name)

        # 3. Check if docker compose network is available
        has_network = False
        try:
            net_check = subprocess.run(
                ["docker", "network", "ls", "-q", "-f", f"name={cls.NETWORK_NAME}"],
                capture_output=True,
                text=True,
                check=False
            )
            has_network = bool(net_check.stdout.strip())
        except Exception:
            has_network = False

        # 4. Construct docker run command with resource limits
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--hostname", "prod-app-server-01",
            "--cap-add", "SYS_PTRACE",
            "--cap-add", "SYS_ADMIN",
            "--security-opt", "seccomp:unconfined",
            "--memory=512m",
            "--cpus=1.0",
            "--pids-limit=256",
            "-e", "TERM=xterm-256color"
        ]

        if has_network:
            cmd.extend(["--network", cls.NETWORK_NAME])

        cmd.append(IMAGE_NAME)

        logger.info(f"Creating isolated sandbox {container_name} for user {user_id}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            logger.error(f"Failed to create container {container_name}: {res.stderr}")
            raise RuntimeError(f"Failed to start isolated sandbox: {res.stderr.strip()}")

        # 5. Wait up to 15s for container to become healthy and services active
        ctrl = LabController(container_name)
        for _ in range(30):
            if ctrl.is_healthy():
                code, out, _ = ctrl.exec_cmd("/usr/local/bin/systemctl is-active web-app", timeout=2)
                if code == 0 and "active" in out:
                    logger.info(f"Sandbox {container_name} is healthy and services active")
                    return container_name
            time.sleep(0.5)

        # Fallback: if container itself is healthy
        if ctrl.is_healthy():
            logger.info(f"Sandbox {container_name} is healthy and ready")
            return container_name

        # If not ready, clean up and raise
        cls.destroy_sandbox(container_name)
        raise RuntimeError(f"Sandbox container {container_name} failed health check within 15 seconds.")

    @classmethod
    def destroy_sandbox(cls, container_name: str) -> bool:
        """Immediately stop and remove a sandbox container."""
        if not container_name:
            return False
        # Prevent accidentally destroying the legacy base container during normal user sandbox cleanup
        if container_name == CONTAINER_NAME:
            return False
        try:
            res = subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False
            )
            return res.returncode == 0
        except Exception as e:
            logger.warning(f"Error destroying sandbox {container_name}: {e}")
            return False

    @classmethod
    def cleanup_user_sandboxes(cls, user_id: str):
        """Find and remove any containers associated with this user."""
        u_prefix = user_id.replace("-", "")[:8]
        filter_name = f"linuxlab-sandbox-{u_prefix}-"

        # Check DB for user's active session container
        active_session = db.get_active_incident_session(user_id)
        if active_session and active_session.get("container_name"):
            cls.destroy_sandbox(active_session["container_name"])

        # Also search docker for any matching containers by prefix
        try:
            res = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={filter_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0 and res.stdout.strip():
                for name in res.stdout.strip().splitlines():
                    cls.destroy_sandbox(name.strip())
        except Exception as e:
            logger.warning(f"Failed to list user containers for cleanup: {e}")

    @classmethod
    def cleanup_orphaned_sandboxes(cls):
        """Cleanup any linuxlab-sandbox-* containers that are no longer active in DB."""
        active_containers = set(db.get_all_active_containers())

        # Cleanup expired sessions from DB first
        stale_sessions = db.get_stale_incident_sessions(max_age_hours=2)
        for s in stale_sessions:
            c_name = s.get("container_name")
            if c_name:
                cls.destroy_sandbox(c_name)
            db.close_incident_session(s["user_id"], status="abandoned")

        try:
            res = subprocess.run(
                ["docker", "ps", "-a", "--filter", "name=linuxlab-sandbox-", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0 and res.stdout.strip():
                for name in res.stdout.strip().splitlines():
                    name = name.strip()
                    # Do not remove legacy base container
                    if name == CONTAINER_NAME:
                        continue
                    if name not in active_containers:
                        logger.info(f"Removing orphaned sandbox: {name}")
                        cls.destroy_sandbox(name)
        except Exception as e:
            logger.warning(f"Failed to cleanup orphaned sandboxes: {e}")

    @classmethod
    def cleanup_expired_sessions(cls, max_age_hours: int = 2):
        """Cleanup any active incident sessions older than max_age_hours and remove their containers."""
        stale_sessions = db.get_stale_incident_sessions(max_age_hours=max_age_hours)
        cleaned = []
        for s in stale_sessions:
            c_name = s.get("container_name")
            if c_name:
                cls.destroy_sandbox(c_name)
            db.close_incident_session(s["user_id"], status="expired")
            cleaned.append(s["id"])
        return cleaned
