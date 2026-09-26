from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class HighCPUScenario(Scenario):
    """Scenario: Runaway analytics process pegging CPU at 100%."""

    id = "cpu_001"
    category = "cpu"
    level = "EASY"
    difficulty = "EASY"
    title = "Runaway Background Worker Pegging CPU"
    symptoms = [
        "API response latency has spiked by over 500%",
        "Prometheus alert firing: NodeCPUUtilizationHigh (>90% CPU usage)",
        "Application threads are starving for CPU execution cycles",
    ]
    context = (
        "The on-call team received automated alerts that prod-app-server-01 is experiencing "
        "severe CPU starvation. End users report that API calls are intermittently timing out. "
        "A deployment was completed 45 minutes ago. You have terminal access as 'devops'."
    )
    objective = (
        "1. Identify the culprit process consuming excessive CPU.\n"
        "2. Safely terminate or remediate the rogue process.\n"
        "3. Verify that CPU utilization returns to a healthy baseline."
    )
    expected_tools = ["top", "ps", "kill", "uptime"]
    investigation_guidance = (
        "Focus on process resource consumption. Run 'ps aux --sort=-%cpu' or launch 'top' "
        "(press 'P' to sort by CPU usage). Locate the process consuming ~100% CPU, note its PID, "
        "and terminate it with 'kill <PID>' or 'kill -9 <PID>'."
    )
    hints = [
        "Inspect the active processes on the system to locate high CPU consumers.",
        "Run 'ps aux --sort=-%cpu | head -n 10' or 'top' to spot the rogue worker process.",
        "Locate the PID running 'worker_loop' and terminate it using 'kill <PID>' (or 'kill -9 <PID>').",
    ]
    expected_root_cause = (
        "A rogue worker process ('worker_loop') was running an unthrottled tight while loop, "
        "pegging a CPU core at 100% and starving legitimate services."
    )
    expected_fix = (
        "Identified the rogue worker process via 'ps aux --sort=-%cpu' or 'top', and terminated it "
        "using 'kill -15 <PID>' (or 'kill -9 <PID>'). Verified with 'top' or 'uptime' that CPU load normalized."
    )
    validation = "Verify with 'ps aux | grep worker_loop' that the process is gone, and confirm 'curl http://localhost:8080/health' returns UP."
    learning_points = [
        "ps aux --sort=-%cpu to immediately identify high-CPU consumers",
        "top / htop interactive navigation (P to sort by CPU)",
        "pidstat -u 1 3 for continuous per-PID CPU sampling",
        "Graceful termination (SIGTERM 15) vs forceful kill (SIGKILL 9)",
    ]
    postmortem_sections = {
        "what_happened": "A rogue background task named 'worker_loop' went into an infinite compute loop consuming 100% of a CPU core.",
        "commands_used": "ps aux --sort=-%cpu | head -n 10; kill -9 <PID>; uptime",
        "output_meaning": "'ps' output showed worker_loop at ~99% %CPU. Terminating it cleared the run queue.",
        "why_fix_worked": "Killing the unconstrained process freed the CPU scheduler to allocate execution cycles to web-app.service."
    }

    def setup(self, controller: LabController) -> bool:
        # Start a runaway worker process in the background inside the container
        setup_cmd = (
            "nohup bash -c 'exec -a worker_loop python3 -c \""
            "import time\n"
            "x = 0\n"
            "while True:\n"
            "    x = (x + 1) % 10000000\n"
            "\"' > /dev/null 2>&1 &"
        )
        code, _, err = controller.exec_cmd(setup_cmd, user="devops")
        if code != 0:
            return False

        # Verify the process is active
        v_code, out, _ = controller.exec_cmd("pgrep -f worker_loop")
        return v_code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check if the rogue process is still running
        code, out, _ = controller.exec_cmd("pgrep -f worker_loop")
        if code == 0 and out.strip():
            pids = out.strip().split()
            return False, f"Worker process is still running with PID(s): {', '.join(pids)}", {"pids": pids}

        # Check web-app is healthy
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        web_healthy = (h_code == 0 and "UP" in h_out)

        if not web_healthy:
            return False, "Rogue process was killed, but the core web-app service is not responding.", {"web_app": "down"}

        return True, "Rogue process successfully terminated. CPU normalized and core services are healthy.", {"web_app": "UP"}
