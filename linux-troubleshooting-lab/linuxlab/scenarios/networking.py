from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class PortConflictScenario(Scenario):
    """Scenario: Port 8080 is occupied by a rogue listener, blocking web-app."""

    id = "net_001"
    category = "networking"
    level = "MODERATE"
    difficulty = "MODERATE"
    title = "Port Conflict Blocking Production Web Service"
    symptoms = [
        "Web application service fails to bind its primary socket",
        "Error in service logs: 'Address already in use' (Errno 98 / EADDRINUSE)",
        "Automated deployment rollbacks triggered",
    ]
    context = (
        "During a service restart on prod-app-server-01, web-app.service failed to bind to port 8080. "
        "The application log reports: 'FATAL: Port conflict on 8080: [Errno 98] Address already in use'. "
        "Determine what rogue process is holding port 8080, terminate it, and restore the web application."
    )
    objective = (
        "1. Identify the rogue process holding port 8080.\n"
        "2. Terminate the rogue listener safely.\n"
        "3. Start web-app.service and verify it successfully binds port 8080."
    )
    expected_tools = ["ss", "lsof", "kill", "systemctl"]
    investigation_guidance = (
        "Investigate open listening ports using 'ss -tulpn' or 'lsof -i :8080'. "
        "Notice the rogue process occupying 0.0.0.0:8080. "
        "Terminate the offending process using 'kill <PID>' and restart 'web-app.service'."
    )
    hints = [
        "Inspect which process is currently listening on port 8080 using socket investigation tools.",
        "Run 'ss -tulpn | grep 8080' or 'lsof -i :8080' to determine the PID holding the socket.",
        "Terminate the rogue process holding port 8080 using 'kill <PID>', then restart 'web-app.service'.",
    ]
    expected_root_cause = (
        "An orphaned test netcat process ('rogue_listener') was actively bound to port 8080, "
        "preventing web-app.service from binding to 0.0.0.0:8080."
    )
    expected_fix = (
        "Used 'ss -tulpn' or 'lsof -i :8080' to discover the rogue PID holding the port, "
        "terminated it via 'kill <PID>', and restarted web-app with 'systemctl restart web-app'."
    )
    validation = "Confirm 'systemctl is-active web-app' returns active and 'curl http://localhost:8080/health' returns UP."
    learning_points = [
        "ss -tulpn vs netstat -tulnp (socket statistics from kernel netlink)",
        "lsof -i :<PORT> to find the exact command and PID holding an open file descriptor or socket",
        "Understanding TCP socket states (LISTEN, TIME_WAIT, CLOSE_WAIT)",
        "SO_REUSEADDR socket options in networking servers",
    ]
    postmortem_sections = {
        "investigation_sequence": "1. journalctl -u web-app (Address already in use) -> 2. ss -tulpn | grep 8080 -> 3. kill <PID> -> 4. systemctl restart web-app",
        "evidence": "'ss -tulpn' identified an orphaned rogue_listener process bound to port 8080.",
        "root_cause": "Orphaned test listener process was never stopped prior to web service startup.",
        "remediation": "Terminated rogue process with SIGTERM/SIGKILL and restarted web-app.",
        "validation_steps": "Verified port 8080 is owned by web-app and health check endpoint returns 200."
    }

    def setup(self, controller: LabController) -> bool:
        # Stop web-app
        controller.exec_cmd("systemctl stop web-app")
        # Launch rogue listener holding port 8080
        setup_cmd = (
            "nohup bash -c 'exec -a rogue_listener nc -l -k -p 8080' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(setup_cmd, user="devops")
        # Attempt to start web-app so it registers the port conflict in logs
        controller.exec_cmd("systemctl start web-app")

        # Verify rogue listener is running
        code, out, _ = controller.exec_cmd("ss -tulpn | grep 8080")
        return code == 0 and "8080" in out

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check rogue listener is terminated
        code, out, _ = controller.exec_cmd("pgrep -f rogue_listener")
        if code == 0 and out.strip():
            return False, "Rogue listener process is still running and occupying port 8080.", {"rogue_pid": out.strip()}

        # Check if web-app is running
        s_code, s_out, _ = controller.exec_cmd("systemctl is-active web-app")
        if s_code != 0 or s_out.strip() != "active":
            return False, "Rogue listener was removed, but web-app.service is not started. Run 'systemctl restart web-app'.", {"active": False}

        # Verify curl returns expected web-app response
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "web-app" not in h_out:
            return False, "Port 8080 is open, but did not respond with web-app health check.", {"health": False}

        return True, "Port conflict resolved and web-app service is responding normally on port 8080.", {"status": "healthy"}
