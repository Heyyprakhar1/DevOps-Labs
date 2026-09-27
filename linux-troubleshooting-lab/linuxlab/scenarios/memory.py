from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class MemoryPressureScenario(Scenario):
    """Scenario: Rogue process hogging RAM causing memory pressure."""

    id = "mem_001"
    category = "memory"
    level = "EASY"
    difficulty = "EASY"
    title = "Rogue Process Exhausting Available Memory"
    symptoms = [
        "System alerts reporting high memory usage and buffer allocation failures",
        "Available memory critically low on prod-app-server-01",
        "Risk of kernel OOM killer terminating critical application daemons",
    ]
    context = (
        "Monitoring fired a warning alert: Available RAM on prod-app-server-01 is below 150MB. "
        "The application team reported cache buffer allocation errors. A batch job was triggered "
        "earlier by an intern. You need to investigate the memory distribution, locate the culprit, "
        "and recover system headroom."
    )
    objective = (
        "1. Identify the process consuming disproportionate physical RAM.\n"
        "2. Safely terminate the culprit process.\n"
        "3. Verify that available memory returns to a healthy level."
    )
    expected_tools = ["free", "top", "ps", "kill"]
    investigation_guidance = (
        "Inspect memory distribution with 'free -m' or 'free -h'. Next, find which process is "
        "holding high RSS memory using 'ps aux --sort=-%mem' or 'top' (press Shift+M to sort by memory). "
        "Identify the rogue PID and terminate it with 'kill <PID>'."
    )
    hints = [
        "First determine whether physical RAM or swap is exhausted by inspecting memory distribution.",
        "Sort active processes by resident memory ('top' -> Shift+M or 'ps aux --sort=-%mem') to isolate the high consumer.",
        "Find the PID of 'mem_eater' via 'ps aux --sort=-%mem | head -n 10' and terminate it with 'kill <PID>'.",
    ]
    expected_root_cause = (
        "An unconstrained test script ('mem_eater') allocated an oversized in-memory buffer without releasing it, "
        "exhausting available RAM on the server."
    )
    expected_fix = (
        "Identified the memory hog process via 'ps aux --sort=-%mem' or 'top' (sorted by RSS), "
        "terminated it using 'kill <PID>', and verified available memory restored via 'free -h'."
    )
    validation = "Check 'free -m' to verify available RAM is restored (>500MB) and verify 'curl http://localhost:8080/health' returns UP."
    learning_points = [
        "free -m / free -h to distinguish used vs buff/cache vs available memory",
        "Difference between Virtual Memory (VSZ) and Resident Set Size (RSS)",
        "ps aux --sort=-%mem and top sorting by memory ('M')",
        "How Linux OOM Killer behaves (oom_score, oom_score_adj)",
    ]
    postmortem_sections = {
        "what_happened": "A script named 'mem_eater' allocated a 350MB bytearray and held it in memory, depleting system RAM.",
        "commands_used": "free -m; ps aux --sort=-%mem | head -n 10; kill -9 <PID>; free -m",
        "output_meaning": "'free -m' showed available memory depleted; 'ps' pinpointed the PID with highest RSS.",
        "why_fix_worked": "Killing the process caused the Linux kernel to release all allocated memory pages back to the free pool."
    }

    def setup(self, controller: LabController) -> bool:
        # Launch memory eater script allocating ~350MB of memory
        setup_cmd = (
            "nohup bash -c 'exec -a mem_eater python3 -c \""
            "import time\n"
            "data = bytearray(350 * 1024 * 1024)\n"
            "time.sleep(7200)\n"
            "\"' > /dev/null 2>&1 &"
        )
        code, _, err = controller.exec_cmd(setup_cmd, user="devops")
        if code != 0:
            return False

        # Verify process is running
        v_code, out, _ = controller.exec_cmd("pgrep -f mem_eater")
        return v_code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check if mem_eater is still running
        code, out, _ = controller.exec_cmd("pgrep -f mem_eater")
        if code == 0 and out.strip():
            pids = out.strip().split()
            return False, f"Memory hog process is still running with PID(s): {', '.join(pids)}", {"pids": pids}

        # Check services
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        web_healthy = (h_code == 0 and "UP" in h_out)
        if not web_healthy:
            return False, "Memory hog was killed, but core services are not responding properly.", {"web_app": "down"}

        return True, "Memory hog terminated. Available memory restored to safe levels.", {"status": "healthy"}
