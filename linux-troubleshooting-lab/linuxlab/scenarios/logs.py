from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class ApplicationLogScenario(Scenario):
    """Scenario: Application failing due to broken downstream host resolution in logs."""

    id = "log_001"
    category = "logs"
    level = "MODERATE"
    difficulty = "MODERATE"
    title = "Application Log Diagnosis of Downstream Database Failure"
    symptoms = [
        "Payment processing requests returning HTTP 500 Internal Server Error",
        "E-commerce checkout transactions failing across the platform",
        "PagerDuty P1 incident: 'Payment Gateway Error Rate > 80%'",
    ]
    context = (
        "An urgent incident was escalated: Customer checkouts are failing with HTTP 500 errors "
        "when calling the payment API endpoint (http://localhost:8000/process-payment). "
        "The service itself is running, but transactions are crashing internally. "
        "Investigate the application logs in /var/log/app/payment.log, identify what is causing "
        "the downstream failure, fix the issue, and verify that transactions succeed."
    )
    objective = (
        "1. Inspect /var/log/app/payment.log to find the root cause of the 500 errors.\n"
        "2. Identify and fix the network/host resolution error.\n"
        "3. Verify that 'curl http://localhost:8000/process-payment' returns HTTP 200 with success status."
    )
    expected_tools = ["tail", "grep", "curl", "vim/nano"]
    investigation_guidance = (
        "Start by inspecting the application log with 'tail -n 50 /var/log/app/payment.log'. "
        "Look for the stack trace showing DatabaseConnectionError. "
        "Check how 'db.internal' is being resolved on this host by inspecting '/etc/hosts' and '/etc/app/payment.conf'. "
        "Correct the destination to 127.0.0.1 and test with curl."
    )
    hints = [
        "Inspect the application log file '/var/log/app/payment.log' using 'tail -n 30' or 'grep -i error'.",
        "Notice the error: 'DatabaseConnectionError: Connection refused to database at db.internal:5432'. Check '/etc/hosts' and '/etc/app/payment.conf'.",
        "Inspect '/etc/hosts'. 'db.internal' is pointing to '127.0.0.99'. Change it to '127.0.0.1' (or change 'db_host' in '/etc/app/payment.conf' to '127.0.0.1'). Then verify with 'curl http://localhost:8000/process-payment'.",
    ]
    expected_root_cause = (
        "An erroneous '/etc/hosts' entry routed 'db.internal' to a blackhole IP '127.0.0.99', "
        "causing the Payment API to throw DatabaseConnectionError on every transaction."
    )
    expected_fix = (
        "Analyzed '/var/log/app/payment.log' for stack traces, spotted the database connection failure to 'db.internal', "
        "corrected '/etc/hosts' to map 'db.internal' to '127.0.0.1' (or updated '/etc/app/payment.conf'), "
        "and confirmed transactions pass with HTTP 200."
    )
    validation = "Confirm 'curl -s http://localhost:8000/process-payment' returns HTTP 200 with status 'success'."
    learning_points = [
        "Systematic log analysis with tail, grep, less, and jq",
        "Distinguishing between application runtime crashes vs upstream/downstream dependency failures",
        "Local name resolution hierarchy: /etc/nsswitch.conf and /etc/hosts before DNS",
        "Testing API endpoints with curl -i (headers + body) and verifying HTTP status codes",
    ]
    postmortem_sections = {
        "investigation_sequence": "1. curl /process-payment (500) -> 2. tail /var/log/app/payment.log (Connection refused db.internal) -> 3. cat /etc/hosts -> 4. fix IP -> 5. verify curl",
        "evidence": "Log trace identified connection refused to db.internal:5432; /etc/hosts routed db.internal to 127.0.0.99.",
        "root_cause": "Blackholed /etc/hosts record prevented downstream database connectivity.",
        "remediation": "Updated /etc/hosts mapping db.internal to localhost (127.0.0.1).",
        "validation_steps": "Triggered live test transaction via curl and verified HTTP 200 success response."
    }

    def setup(self, controller: LabController) -> bool:
        # Update /etc/app/payment.conf to use db.internal
        conf = '{"port": 8000, "db_host": "db.internal", "db_port": 5432, "timeout": 3}'
        controller.exec_cmd(f"cat << 'EOF' | sudo tee /etc/app/payment.conf > /dev/null\n{conf}\nEOF")

        # Inject broken /etc/hosts entry
        controller.exec_cmd("grep -v 'db.internal' /etc/hosts | sudo tee /etc/hosts > /dev/null")
        controller.exec_cmd("echo '127.0.0.99 db.internal # linuxlab-injected' | sudo tee -a /etc/hosts")

        # Restart payment-api
        controller.exec_cmd("systemctl restart payment-api")

        # Trigger a failed transaction so error log is populated immediately
        controller.exec_cmd("curl -s http://localhost:8000/process-payment")

        # Verify it returns 500
        code, out, _ = controller.exec_cmd("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/process-payment")
        return out.strip() == "500"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Test payment endpoint
        code, out, _ = controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        if "success" not in out:
            # Check http status
            _, code_out, _ = controller.exec_cmd("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/process-payment")
            return False, f"Payment API is still failing with HTTP status {code_out.strip()}: {out.strip()}", {"response": out.strip()}

        return True, "Payment API transactions are succeeding with HTTP 200 OK.", {"status": "success"}
