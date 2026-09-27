import json
from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class ServiceUnavailableScenario(Scenario):
    """Scenario: Service failing due to corrupted configuration syntax."""

    id = "service_001"
    category = "services"
    level = "MODERATE"
    difficulty = "MODERATE"
    title = "Application Service Crash on Malformed Configuration"
    symptoms = [
        "Web application service is completely down",
        "Attempts to start the service fail immediately",
        "Connections to port 8080 are refused",
    ]
    context = (
        "An incident alert triggered: Internal web-app service on prod-app-server-01 is unreachable. "
        "A team member committed an edit to the service configuration file right before the outage. "
        "Investigate the service logs, identify the root cause of the startup crash, fix the issue, "
        "and bring the service back to a running state."
    )
    objective = (
        "1. Diagnose why web-app.service refuses to start.\n"
        "2. Identify and repair the corrupted configuration file.\n"
        "3. Start web-app.service and verify the HTTP health check passes."
    )
    expected_tools = ["systemctl", "journalctl", "jq", "python3"]
    investigation_guidance = (
        "Check why the service crashed with 'systemctl status web-app' or 'journalctl -u web-app'. "
        "Look for the stack trace pointing to a configuration syntax error. "
        "Validate the configuration file '/etc/app/web_app.conf' using 'python3 -m json.tool' or 'jq .', "
        "repair the syntax, and restart the service with 'systemctl restart web-app'."
    )
    hints = [
        "Check why the service crashed using 'systemctl status web-app' or 'journalctl -u web-app'.",
        "Notice the JSONDecodeError in '/etc/app/web_app.conf'. Validate syntax using 'python3 -m json.tool /etc/app/web_app.conf'.",
        "Open '/etc/app/web_app.conf' and remove the malformed syntax error. Then run 'systemctl restart web-app'.",
    ]
    expected_root_cause = (
        "The configuration file '/etc/app/web_app.conf' contained invalid JSON syntax ('BROKEN_SYNTAX_ERROR'), "
        "causing json.load() to raise a fatal JSONDecodeError on application startup."
    )
    expected_fix = (
        "Inspected journalctl/systemctl crash logs, found JSON syntax error in '/etc/app/web_app.conf', "
        "repaired the JSON file, and successfully started the service via 'systemctl restart web-app'."
    )
    validation = "Confirm 'systemctl is-active web-app' returns active and 'curl http://localhost:8080/health' returns HTTP 200 UP."
    learning_points = [
        "Validating configuration files prior to restarting critical services (e.g. nginx -t, sshd -t, jq)",
        "Interpreting Python stack traces from systemd / journalctl logs",
        "Service lifecycle management with systemctl start / restart / status",
        "Config validation in CI/CD pipelines to prevent syntax regressions",
    ]
    postmortem_sections = {
        "investigation_sequence": "1. systemctl status web-app -> 2. journalctl -u web-app -> 3. python3 -m json.tool /etc/app/web_app.conf -> 4. edit & fix -> 5. systemctl restart",
        "evidence": "Crash trace showed JSONDecodeError at line 5 in /etc/app/web_app.conf.",
        "root_cause": "Invalid non-JSON token committed directly to the production service configuration.",
        "remediation": "Restored clean JSON structure with valid keys.",
        "validation_steps": "Verified JSON validity with jq/json.tool, verified active state with systemctl, tested /health endpoint."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd("systemctl stop web-app")
        broken_json = '{\n  "port": 8080,\n  "workers": 4,\n  "debug": false,\n  BROKEN_SYNTAX_ERROR\n}'
        controller.exec_cmd(f"cat << 'EOF' > /etc/app/web_app.conf\n{broken_json}\nEOF")
        # Attempt start so error shows in logs
        controller.exec_cmd("systemctl start web-app")

        code, out, _ = controller.exec_cmd("systemctl is-active web-app")
        return code != 0 or out.strip() != "active"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Validate JSON in config file
        c_code, c_out, _ = controller.exec_cmd("python3 -m json.tool /etc/app/web_app.conf")
        if c_code != 0:
            return False, "The configuration file '/etc/app/web_app.conf' still contains invalid JSON syntax.", {"valid_json": False}

        # Check if service is active
        s_code, s_out, _ = controller.exec_cmd("systemctl is-active web-app")
        if s_code != 0 or s_out.strip() != "active":
            return False, "Configuration syntax is fixed, but web-app.service has not been started yet. Run 'systemctl restart web-app'.", {"active": False}

        # Verify endpoint
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "Service is running, but the HTTP health check did not return HTTP 200 UP.", {"health": False}

        return True, "Configuration repaired and web-app service is running and healthy.", {"status": "healthy"}


class StoppedServiceScenario(Scenario):
    """Scenario: Essential system service is stopped and needs to be started."""

    id = "easy_005"
    category = "services"
    level = "EASY"
    difficulty = "EASY"
    title = "Critical Web Application Service Is Inactive"
    symptoms = [
        "Web application service is not responding to requests",
        "Attempts to connect to port 8080 result in connection refused",
        "Load balancer reports target node unhealthy",
    ]
    context = (
        "During a routine server reboot, the web-app daemon was stopped and did not start. "
        "Users report that the application homepage is completely unreachable. "
        "You have SSH access as 'devops'. Check the service state and bring it online."
    )
    objective = (
        "1. Check the status of web-app.service.\n"
        "2. Start the service using systemctl.\n"
        "3. Verify that the health check endpoint returns HTTP 200 UP."
    )
    expected_tools = ["systemctl", "curl"]
    investigation_guidance = (
        "Check service status using 'systemctl status web-app'. "
        "If it is inactive (dead), start it using 'systemctl start web-app'. "
        "Verify service recovery with 'curl http://localhost:8080/health'."
    )
    hints = [
        "First determine the operational status of the core application service.",
        "Notice the service is inactive (dead). Start the service unit to bring it online.",
        "Run 'systemctl start web-app' and verify recovery with 'curl http://localhost:8080/health'.",
    ]
    expected_root_cause = "The web-app.service daemon was stopped and inactive."
    expected_fix = "Started the service via 'systemctl start web-app' and verified endpoint health."
    validation = "Confirm 'systemctl is-active web-app' returns active and 'curl http://localhost:8080/health' returns UP."
    learning_points = [
        "Checking service state with systemctl status and is-active",
        "Starting services with systemctl start",
        "Testing HTTP endpoints with curl to confirm end-to-end functionality",
    ]
    postmortem_sections = {
        "what_happened": "The web-app daemon was stopped following maintenance, causing all port 8080 requests to fail.",
        "commands_used": "systemctl status web-app; systemctl start web-app; curl http://localhost:8080/health",
        "output_meaning": "'systemctl status' showed 'inactive (dead)'; starting it restored the process.",
        "why_fix_worked": "Starting the systemd unit spawned the Python HTTP server process on port 8080."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd("systemctl stop web-app")
        code, out, _ = controller.exec_cmd("systemctl is-active web-app")
        return code != 0 or out.strip() != "active"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        s_code, s_out, _ = controller.exec_cmd("systemctl is-active web-app")
        if s_code != 0 or s_out.strip() != "active":
            return False, "web-app.service is still inactive. Run 'systemctl start web-app'.", {"active": False}

        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "Service is active but health check did not return HTTP 200 UP.", {"health": False}

        return True, "web-app service is active and responding to health checks.", {"status": "healthy"}
