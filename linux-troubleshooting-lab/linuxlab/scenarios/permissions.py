from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class FilePermissionsScenario(Scenario):
    """Scenario: Service crashing due to restrictive file permissions on configuration."""

    id = "perm_001"
    category = "permissions"
    level = "EASY"
    difficulty = "EASY"
    title = "Service Failing Due to Restrictive File Permissions"
    symptoms = [
        "The web application service crashed and cannot start",
        "Attempts to restart the service fail with exit-code 1",
        "Endpoints on port 8080 are refusing connections",
    ]
    context = (
        "Following an automated security hardening run on prod-app-server-01, "
        "the internal web-app service failed to restart. Users cannot reach the application. "
        "You have SSH/terminal access as 'devops'. Diagnose why the service is failing, "
        "fix the permission issue, and bring the service back online."
    )
    objective = (
        "1. Check the service status and logs to determine why startup fails.\n"
        "2. Identify the misconfigured file permissions or ownership.\n"
        "3. Correct the permissions (chmod / chown) and start the service successfully."
    )
    expected_tools = ["systemctl", "journalctl", "ls", "chmod"]
    investigation_guidance = (
        "Inspect the service failure using 'systemctl status web-app'. "
        "Notice the error indicating a permission problem accessing '/etc/app/web_app.conf'. "
        "Inspect the permissions with 'ls -la /etc/app/web_app.conf'. "
        "Grant read access using 'sudo chmod 644 /etc/app/web_app.conf', then restart the service."
    )
    hints = [
        "Inspect why the service failed by checking the service status and logs.",
        "Notice the permission denial error. Inspect file permissions on '/etc/app/web_app.conf' using 'ls -la /etc/app/'.",
        "Set readable permissions with 'sudo chmod 644 /etc/app/web_app.conf', then restart with 'systemctl restart web-app'.",
    ]
    expected_root_cause = (
        "The configuration file '/etc/app/web_app.conf' had its read permissions stripped (mode 0000), "
        "causing the Python service to crash with PermissionError [Errno 13] on startup."
    )
    expected_fix = (
        "Inspected 'systemctl status web-app' to find the permission error, applied 'sudo chmod 644 /etc/app/web_app.conf', "
        "and restarted the service with 'systemctl restart web-app'."
    )
    validation = "Confirm 'systemctl is-active web-app' reports active and 'curl http://localhost:8080/health' returns HTTP 200 UP."
    learning_points = [
        "Reading systemd unit crash logs with systemctl status and journalctl -u",
        "Standard Linux permission modes (r=4, w=2, x=1) and chmod octal syntax",
        "Principle of least privilege vs necessary read access for daemon processes",
        "namei -l /path/to/file to inspect entire directory traversal permissions",
    ]
    postmortem_sections = {
        "what_happened": "Security hardening set permissions on '/etc/app/web_app.conf' to 000, preventing the service from reading its config.",
        "commands_used": "systemctl status web-app; ls -la /etc/app/web_app.conf; sudo chmod 644 /etc/app/web_app.conf; systemctl restart web-app",
        "output_meaning": "'PermissionError: [Errno 13] Permission denied' pointed straight to the config file.",
        "why_fix_worked": "chmod 644 granted read permission to all users, enabling the Python process to parse its JSON configuration."
    }

    def setup(self, controller: LabController) -> bool:
        # Stop service
        controller.exec_cmd("systemctl stop web-app")
        # Strip permissions on config file
        controller.exec_cmd("sudo chmod 000 /etc/app/web_app.conf")
        # Attempt restart so the failure logs show in systemctl
        controller.exec_cmd("systemctl start web-app")
        
        # Verify it is dead
        code, out, _ = controller.exec_cmd("systemctl is-active web-app")
        return code != 0 or out.strip() != "active"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check permissions on /etc/app/web_app.conf
        code, out, _ = controller.exec_cmd("stat -c '%a' /etc/app/web_app.conf")
        mode = out.strip()
        if mode in ["0", "000", "200", "300"]:
            return False, f"Config file /etc/app/web_app.conf still has restrictive permissions ({mode}).", {"mode": mode}

        # Check if service is active
        s_code, s_out, _ = controller.exec_cmd("systemctl is-active web-app")
        if s_code != 0 or s_out.strip() != "active":
            return False, "Permissions look better, but web-app.service is still not running. Did you restart the service?", {"service_status": s_out.strip()}

        # Verify HTTP endpoint
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "Service is running but not responding to health check requests on port 8080.", {"health": "fail"}

        return True, "Permissions corrected and web-app service is running and healthy.", {"status": "healthy"}


class LogFilePermissionScenario(Scenario):
    """Scenario: Service crashing because its log file is owned by root with restrictive permissions."""

    id = "mod_005"
    category = "permissions"
    level = "MODERATE"
    difficulty = "MODERATE"
    title = "Application Crash Due to Log File Ownership Mismatch"
    symptoms = [
        "payment-api.service crashes on startup with exit status 1",
        "Error in journalctl: PermissionError: [Errno 13] Permission denied: '/var/log/app/payment.log'",
        "Payment transactions are completely offline",
    ]
    context = (
        "During an emergency maintenance task, an engineer ran a diagnostic command as root "
        "that recreated '/var/log/app/payment.log' owned by root:root with mode 600. "
        "When payment-api restarts under the 'devops' user, it crashes immediately on initialization. "
        "Investigate the service logs, fix the file ownership/permissions, and restart the service."
    )
    objective = (
        "1. Inspect service logs to determine why payment-api crashes on startup.\n"
        "2. Identify the ownership mismatch on '/var/log/app/payment.log'.\n"
        "3. Restore ownership to 'devops:devops', restart payment-api, and verify HTTP 200 health."
    )
    expected_tools = ["systemctl", "journalctl", "ls", "chown", "curl"]
    investigation_guidance = (
        "Run 'journalctl -u payment-api' or 'systemctl status payment-api' to inspect the stack trace. "
        "Notice the PermissionError pointing to '/var/log/app/payment.log'. "
        "Check file ownership with 'ls -la /var/log/app/payment.log'. "
        "Change ownership to devops with 'sudo chown devops:devops /var/log/app/payment.log' (or chmod 666), "
        "then restart with 'systemctl restart payment-api'."
    )
    hints = [
        "Inspect the service crash log using 'journalctl -u payment-api'.",
        "Notice PermissionError on '/var/log/app/payment.log'. Inspect ownership with 'ls -la /var/log/app/'.",
        "Restore ownership with 'sudo chown devops:devops /var/log/app/payment.log' and run 'systemctl restart payment-api'.",
    ]
    expected_root_cause = (
        "The log file '/var/log/app/payment.log' was owned by 'root:root' with mode 0600, "
        "preventing the unprivileged service user 'devops' from opening the file for logging."
    )
    expected_fix = (
        "Inspected journalctl, identified the ownership conflict on '/var/log/app/payment.log', "
        "ran 'sudo chown devops:devops /var/log/app/payment.log', and restarted payment-api."
    )
    validation = "Confirm 'systemctl is-active payment-api' returns active and 'curl http://localhost:8000/health' returns UP."
    learning_points = [
        "Linux daemon execution context and UID/GID permission boundaries",
        "Distinguishing read permissions (chmod) vs owner/group attributes (chown)",
        "Why running diagnostic tools as root can inadvertently break daemon log files",
    ]
    postmortem_sections = {
        "investigation_sequence": "1. systemctl status payment-api -> 2. journalctl -u payment-api -> 3. ls -la /var/log/app/payment.log -> 4. sudo chown devops:devops -> 5. systemctl restart",
        "evidence": "Log output showed PermissionError: [Errno 13] on /var/log/app/payment.log owned by root:root 0600.",
        "root_cause": "Root diagnostic execution modified ownership of the active application log file.",
        "remediation": "Restored file ownership to devops:devops.",
        "validation_steps": "Verified payment-api service is active and /health returns HTTP 200 UP."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd("systemctl stop payment-api")
        controller.exec_cmd("sudo touch /var/log/app/payment.log && sudo chown root:root /var/log/app/payment.log && sudo chmod 600 /var/log/app/payment.log")
        controller.exec_cmd("systemctl start payment-api")
        code, out, _ = controller.exec_cmd("systemctl is-active payment-api")
        return code != 0 or out.strip() != "active"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check if service is active
        s_code, s_out, _ = controller.exec_cmd("systemctl is-active payment-api")
        if s_code != 0 or s_out.strip() != "active":
            return False, "payment-api.service is not running. Check file ownership and restart.", {"active": False}

        # Check health endpoint
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8000/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "payment-api is running but not responding to health check.", {"health": False}

        return True, "Log ownership resolved and payment-api is running healthy.", {"status": "healthy"}
