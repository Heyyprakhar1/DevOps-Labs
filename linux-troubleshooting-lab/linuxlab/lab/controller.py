import subprocess
import shlex
import time
from typing import Tuple, Optional
from linuxlab.config import CONTAINER_NAME, COMPOSE_FILE, ROOT_DIR

class LabController:
    """Manages the disposable Docker container lifecycle and command execution."""

    def __init__(self, container_name: str = CONTAINER_NAME):
        self.container_name = container_name

    def is_running(self) -> bool:
        """Check if the lab container is currently running."""
        try:
            res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.container_name],
                capture_output=True,
                text=True,
                check=False
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def is_healthy(self) -> bool:
        """Check if lab container is running and responds to commands."""
        if not self.is_running():
            return False
        code, out, _ = self.exec_cmd("echo ping", timeout=5)
        return code == 0 and "ping" in out

    def start(self) -> bool:
        """Start or build the lab container if not running."""
        if self.is_running():
            return True
        try:
            res = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode != 0:
                return False
            # Wait up to 15s for container to become ready
            for _ in range(30):
                if self.is_healthy():
                    return True
                time.sleep(0.5)
            return False
        except Exception:
            return False

    def stop(self) -> bool:
        """Stop the lab container."""
        try:
            res = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "stop"],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                check=False
            )
            return res.returncode == 0
        except Exception:
            return False

    def reset(self) -> bool:
        """Run clean_state.sh inside the container to reset it to baseline."""
        self.ensure_running()
        code, out, err = self.exec_cmd("/opt/scripts/clean_state.sh", user="devops", timeout=20)
        return code == 0

    def ensure_running(self):
        """Ensure the container is running; raise exception if it cannot start."""
        if not self.is_running():
            success = self.start()
            if not success:
                raise RuntimeError("Failed to start the Linux Lab sandbox container. Make sure Docker is running.")

    def exec_cmd(self, cmd: str, user: str = "devops", timeout: int = 30) -> Tuple[int, str, str]:
        """Execute a bash command inside the container safely."""
        self.ensure_running()
        docker_cmd = [
            "docker", "exec",
            "-u", user,
            self.container_name,
            "/bin/bash", "-c", cmd
        ]
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return -1, "", str(e)

    def interactive_shell(self, user: str = "devops"):
        """Attach user's current terminal directly to the container bash shell."""
        self.ensure_running()
        cmd = ["docker", "exec", "-it", "-u", user, self.container_name, "/bin/bash"]
        subprocess.run(cmd)
