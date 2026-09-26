import time
from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class StaleLockScenario(Scenario):
    """Scenario: Stale PID file prevents service from starting cleanly."""

    id = "fluent_001"
    category = "services"
    level = "FLUENT"
    difficulty = "FLUENT"
    title = "Service Startup Aborted by Stale Process Lock"
    symptoms = [
        "Web application endpoint on port 8080 is unresponsive",
        "systemctl reports web-app is running with PID 1, but HTTP health checks fail",
        "Application startup aborted due to stale runtime lock",
    ]
    context = (
        "Following an abrupt container node failover, the web application service is completely unreachable. "
        "The on-call engineer attempted to check the service, but noticed confusing output: "
        "'systemctl status web-app' claims the service is active with PID 1, yet port 8080 refuses connections. "
        "Investigate the runtime service state, eliminate the stale lock, and restore the service."
    )
    objective = (
        "1. Diagnose the discrepancy between systemctl status and actual socket availability.\n"
        "2. Identify and clear the stale PID/lock state in /run/services/.\n"
        "3. Restart web-app.service and confirm HTTP 200 on port 8080."
    )
    expected_tools = ["systemctl", "ss", "curl", "rm", "ps"]
    investigation_guidance = (
        "Check actual socket availability on port 8080 with 'ss -lntp'. "
        "Observe that no process is listening on 8080 despite systemctl status showing PID 1. "
        "Inspect '/run/services/web-app.pid'. Remove the stale PID file or run 'systemctl stop web-app', "
        "then execute 'systemctl start web-app' to launch the real daemon."
    )
    hints = [
        "Correlate service status with actual listening sockets using 'ss -lntp | grep 8080'.",
        "Inspect the contents of '/run/services/web-app.pid'. Does the PID belong to the actual python web service?",
        "Remove the stale file '/run/services/web-app.pid' using 'rm -f' and run 'systemctl restart web-app'.",
    ]
    expected_root_cause = (
        "A stale PID file '/run/services/web-app.pid' remained from an unclean shutdown containing PID 1, "
        "fooling systemctl into believing the service was active while no process was listening on port 8080."
    )
    expected_fix = (
        "Removed the stale PID file '/run/services/web-app.pid' and issued 'systemctl start web-app', "
        "successfully spawning the Python web service and binding port 8080."
    )
    validation = "Confirm 'ss -lntp | grep 8080' shows python3 and 'curl http://localhost:8080/health' returns UP."
    learning_points = [
        "PID file mechanics: how init scripts and process managers determine service health",
        "Why socket probes (curl / ss) are more authoritative than PID file existence",
        "Graceful cleanup and trapping SIGTERM to prevent orphaned runtime artifacts",
    ]
    postmortem_sections = {
        "methodology": "Observed symptom (port 8080 refused) -> Tested hypothesis (service running vs dead) -> Inspected runtime directory /run/services/ -> Cleared stale lock -> Verified socket.",
        "evidence": "PID file contained '1', which is always alive in containers, causing false-positive status reporting.",
        "root_cause": "Orphaned runtime state masked an offline service daemon.",
        "remediation": "Purged stale PID file and cleanly launched daemon.",
        "prevention": "Ensure unit files clean PID files on startup or use systemd RuntimeDirectory=."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd("systemctl stop web-app")
        # Put PID 1 into the pid file so systemctl thinks it's active
        controller.exec_cmd("echo '1' > /run/services/web-app.pid")
        code, out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        return code != 0 or "UP" not in out

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Verify port 8080 has real listener
        code, out, _ = controller.exec_cmd("ss -tulpn | grep 8080")
        if code != 0 or "8080" not in out:
            return False, "Port 8080 is not listening. The service daemon has not been started properly.", {"port": "closed"}

        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "Service is running on port 8080 but failed the /health check.", {"health": "fail"}

        return True, "Stale PID lock resolved and web-app is healthy on port 8080.", {"status": "healthy"}


class OpenDeletedFileScenario(Scenario):
    """Scenario: An unlinked open file descriptor holds disk space after deletion."""

    id = "fluent_002"
    category = "disk"
    level = "FLUENT"
    difficulty = "FLUENT"
    title = "Storage Capacity Alert Persists After File Deletion"
    symptoms = [
        "Filesystem capacity alert firing: /var/log space utilization exceeds 85%",
        "Directory inspection with 'du -sh /var/log/app/*' shows only a few megabytes",
        "Attempts to free space with 'rm' appeared to succeed but 'df -h' did not change",
    ]
    context = (
        "An on-call engineer received a disk capacity alert on prod-app-server-01. "
        "They identified '/var/log/app/stream_leak.log' and deleted it with 'rm'. "
        "However, Prometheus still reports the disk is full! 'du -sh' cannot find the missing 300MB. "
        "Diagnose why the filesystem has not released the storage blocks, locate the culprit, and free the space."
    )
    objective = (
        "1. Reconcile the discrepancy between df (filesystem blocks) and du (directory tree).\n"
        "2. Locate the process holding an open file descriptor to the unlinked file.\n"
        "3. Free the held disk space and verify capacity recovery via df."
    )
    expected_tools = ["df", "du", "lsof", "kill"]
    investigation_guidance = (
        "Compare 'df -h' and 'du -sh /var/log'. The difference indicates an open deleted file. "
        "Run 'lsof +L1' or 'lsof | grep deleted' to locate open file descriptors with link count 0. "
        "Note the PID of the holding process ('stream_leak') and terminate it with 'kill <PID>'."
    )
    hints = [
        "In Linux, unlinking a file with 'rm' does not release disk blocks if a running process holds an open file descriptor.",
        "Use 'lsof +L1' or 'lsof | grep deleted' to find processes holding open handles to unlinked files.",
        "Locate the PID of 'stream_leak' from the lsof output and terminate it using 'kill <PID>'.",
    ]
    expected_root_cause = (
        "A background process ('stream_leak') was actively writing to '/var/log/app/stream_leak.log'. "
        "Deleting the file with 'rm' unlinked the directory entry, but the inode and data blocks remained allocated "
        "because the file descriptor remained open."
    )
    expected_fix = (
        "Used 'lsof +L1' or 'lsof | grep deleted' to identify the process holding the unlinked descriptor, "
        "terminated it via 'kill <PID>', and verified storage reclamation with 'df -h'."
    )
    validation = "Confirm 'lsof | grep deleted' no longer shows stream_leak and verify df shows reclaimed space."
    learning_points = [
        "How Linux handles unlinked open file descriptors (dentry vs inode reference count)",
        "Why 'df' queries superblock block maps while 'du' traverses directory trees",
        "Safely truncating active logs (> file.log) vs deleting active logs with rm",
    ]
    postmortem_sections = {
        "methodology": "Observed df vs du discrepancy -> Formulated hypothesis (open unlinked descriptor) -> Verified with lsof +L1 -> Terminated holding PID -> Re-checked df.",
        "evidence": "'lsof | grep deleted' showed stream_leak process holding a 300MB unlinked file.",
        "root_cause": "Log file was deleted with rm while the logging process remained running.",
        "remediation": "Terminated the holding process, allowing the kernel to decrement the inode reference count to 0 and free the blocks.",
        "prevention": "Configure logrotate with 'copytruncate' or signal SIGHUP to daemons on log rotation."
    }

    def setup(self, controller: LabController) -> bool:
        # Launch python process creating 300MB file, unlinking it, and holding descriptor open
        cmd = (
            "nohup bash -c 'exec -a stream_leak python3 -c \""
            "import os, time\n"
            "path = \\\"/var/log/app/stream_leak.log\\\"\n"
            "with open(path, \\\"wb\\\") as f:\n"
            "    f.write(b\\\"X\\\" * (300 * 1024 * 1024))\n"
            "    f.flush()\n"
            "    os.unlink(path)\n"
            "    time.sleep(7200)\n"
            "\"' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(cmd, user="devops")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("pgrep -f stream_leak")
        return code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("pgrep -f stream_leak")
        if code == 0 and out.strip():
            return False, f"Process 'stream_leak' is still running with PID {out.strip()} holding the open file descriptor.", {"pid": out.strip()}

        return True, "Open deleted file descriptor released and disk space reclaimed.", {"status": "healthy"}


class ServicePortMismatchScenario(Scenario):
    """Scenario: Service configured to listen on wrong port after deployment."""

    id = "fluent_003"
    category = "networking"
    level = "FLUENT"
    difficulty = "FLUENT"
    title = "Microservice Port Configuration Mismatch After Deploy"
    symptoms = [
        "Internal payment gateway reports connection refused on port 8000",
        "payment-api.service reports active and running in systemctl",
        "E-Commerce checkouts failing across all client sessions",
    ]
    context = (
        "A deployment rollout updated configuration files on prod-app-server-01. "
        "The payment API service started cleanly, but upstream proxies and clients are unable to connect to port 8000. "
        "Investigate the service configuration and network sockets, correct the port binding, and verify transactions."
    )
    objective = (
        "1. Identify the port on which payment-api is actually listening.\n"
        "2. Reconfigure /etc/app/payment.conf to bind to the standard port (8000).\n"
        "3. Restart payment-api and verify 'curl http://localhost:8000/process-payment' returns HTTP 200."
    )
    expected_tools = ["ss", "systemctl", "jq", "curl", "vim/nano"]
    investigation_guidance = (
        "Check which port payment-api is listening on with 'ss -tulpn'. "
        "Notice it is listening on port 8005 instead of 8000. "
        "Inspect '/etc/app/payment.conf'. Change 'port': 8005 to 'port': 8000, "
        "restart with 'systemctl restart payment-api', and test with curl."
    )
    hints = [
        "The service is running, but on what socket? Inspect listening TCP ports with 'ss -tulpn'.",
        "Notice the process is listening on port 8005. Check '/etc/app/payment.conf'.",
        "Edit '/etc/app/payment.conf', change 'port': 8005 to 8000, and run 'systemctl restart payment-api'.",
    ]
    expected_root_cause = (
        "A configuration error in '/etc/app/payment.conf' set the server port to 8005 instead of standard port 8000, "
        "causing all incoming checkout requests directed to 8000 to be refused."
    )
    expected_fix = (
        "Identified the listening port via 'ss -tulpn', updated 'port': 8000 in '/etc/app/payment.conf', "
        "and restarted payment-api via 'systemctl restart payment-api'."
    )
    validation = "Confirm 'ss -tulpn | grep 8000' shows payment-api and 'curl http://localhost:8000/process-payment' returns 200 success."
    learning_points = [
        "Inspecting network sockets with ss -tulpn to verify port bindings",
        "Reconciling infrastructure configuration with service-level parameters",
        "Health checking actual service ports following deployment rollouts",
    ]
    postmortem_sections = {
        "methodology": "Client connection failure -> Validated daemon running -> Checked socket binding with ss -> Found port drift -> Corrected configuration -> Verified end-to-end.",
        "evidence": "'ss -tulpn' revealed payment_api bound to 0.0.0.0:8005 while clients connected to 8000.",
        "root_cause": "Configuration drift: port parameter was modified to 8005 in /etc/app/payment.conf.",
        "remediation": "Restored port configuration to 8000 and restarted service.",
        "prevention": "Implement configuration schema validation in CI/CD pipeline."
    }

    def setup(self, controller: LabController) -> bool:
        conf = '{"port": 8005, "db_host": "127.0.0.1", "db_port": 5432, "timeout": 3}'
        controller.exec_cmd(f"cat << 'EOF' | sudo tee /etc/app/payment.conf > /dev/null\n{conf}\nEOF")
        controller.exec_cmd("systemctl restart payment-api")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health")
        return out.strip() != "200"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check listening port 8000
        code, out, _ = controller.exec_cmd("ss -tulpn | grep 8000")
        if code != 0 or "8000" not in out:
            return False, "payment-api is not listening on port 8000.", {"port_8000": False}

        # Check process-payment returns success
        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        if "success" not in h_out:
            return False, "Port 8000 is open but payment transactions did not succeed.", {"response": h_out}

        return True, "Port configuration restored and payment transactions succeeding on port 8000.", {"status": "healthy"}


class DisguisedProcessCPUScenario(Scenario):
    """Scenario: A high CPU process disguised as a kernel thread / systemd task."""

    id = "fluent_004"
    category = "cpu"
    level = "FLUENT"
    difficulty = "FLUENT"
    title = "Disguised Background Task Siphoning CPU Under System Thread Name"
    symptoms = [
        "Host CPU utilization sustained above 90%",
        "Application requests experiencing 400% latency regression",
        "Team members report no scheduled batch jobs are running",
    ]
    context = (
        "Monitoring fired an alert: prod-app-server-01 CPU saturation exceeds 90%. "
        "A quick glance at top shows high CPU, but the process name appears to be a system daemon '[kworker_flush]'. "
        "Investigate the process hierarchy, determine if the process is a legitimate kernel thread or an imposter, "
        "and terminate the culprit."
    )
    objective = (
        "1. Distinguish between true kernel threads (UID 0, parent PID 2) and masquerading user processes.\n"
        "2. Locate the disguised process consuming abnormal CPU.\n"
        "3. Terminate the rogue worker and verify CPU normalization."
    )
    expected_tools = ["top", "ps", "kill", "uptime"]
    investigation_guidance = (
        "Inspect processes with 'ps -eo pid,user,%cpu,ppid,args --sort=-%cpu | head -n 10'. "
        "Notice the high-CPU process named '[kworker_flush]' is running under user 'devops' (not root) "
        "and has a normal parent PID (not kernel PID 2). "
        "Terminate the rogue process with 'kill -9 <PID>'."
    )
    hints = [
        "Kernel threads always run as root (UID 0) and have PPID 2 (kthreadd). Check the UID and PPID of the high CPU task.",
        "Run 'ps -eo pid,user,ppid,%cpu,args --sort=-%cpu | head -n 10' to inspect the disguised process.",
        "Terminate the disguised process using 'pkill -9 -f kworker_flush' (or kill <PID>).",
    ]
    expected_root_cause = (
        "A user-space Python script masqueraded as a kernel worker thread ('[kworker_flush]') "
        "while executing an unthrottled computation loop consuming 100% of a CPU core."
    )
    expected_fix = (
        "Identified the imposter process by checking UID and PPID via 'ps -eo pid,user,ppid,%cpu,args', "
        "and terminated it with 'kill -9 <PID>'."
    )
    validation = "Confirm CPU load drops and 'pgrep -f kworker_flush' returns no active processes."
    learning_points = [
        "Distinguishing genuine Linux kernel threads (PPID 2, square brackets) from masquerading user processes",
        "Inspecting /proc/<PID>/exe and /proc/<PID>/status to reveal true binary paths",
        "Using ps -eo formatting for security and SRE process auditing",
    ]
    postmortem_sections = {
        "methodology": "High CPU alert -> Inspected process table -> Examined process attributes (UID != root, PPID != 2) -> Confirmed masquerade -> Terminated process -> Validated baseline.",
        "evidence": "Process '[kworker_flush]' was owned by UID 1000 (devops) and executed python3 bytecode.",
        "root_cause": "Rogue workload was executed with exec -a to disguise its command name.",
        "remediation": "Killed process via SIGKILL and verified CPU utilization dropped to <5%.",
        "prevention": "Implement process anomaly detection and restrict execution permissions."
    }

    def setup(self, controller: LabController) -> bool:
        cmd = (
            "nohup bash -c 'exec -a \"[kworker_flush]\" python3 -c \""
            "import time\n"
            "x = 0\n"
            "while True:\n"
            "    x = (x + 1) % 10000000\n"
            "\"' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(cmd, user="devops")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("pgrep -f kworker_flush")
        return code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("pgrep -f kworker_flush")
        if code == 0 and out.strip():
            return False, f"Disguised process is still active with PID(s): {out.strip()}", {"pids": out.strip()}

        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "Disguised process was killed but web-app is not responding.", {"health": "fail"}

        return True, "Disguised CPU consumer terminated and system health normalized.", {"status": "healthy"}


class DatabasePortMisconfigurationScenario(Scenario):
    """Scenario: Downstream database port misconfigured in payment.conf."""

    id = "fluent_005"
    category = "logs"
    level = "FLUENT"
    difficulty = "FLUENT"
    title = "Downstream Database Connection Failure Due to Port Misconfiguration"
    symptoms = [
        "Payment processing endpoint returning HTTP 500 Internal Server Error",
        "Customer checkouts failing at payment submission step",
        "Payment API service is running, but downstream connectivity fails",
    ]
    context = (
        "Following an update to the database connection parameters, customer checkout transactions "
        "began failing with HTTP 500. The payment-api daemon is running, but logs report connectivity errors. "
        "Analyze the application log, locate the faulty connection parameter in /etc/app/payment.conf, "
        "and restore successful transactions."
    )
    objective = (
        "1. Inspect /var/log/app/payment.log to find the specific connection error.\n"
        "2. Identify the incorrect port setting in /etc/app/payment.conf.\n"
        "3. Correct the port to 5432, restart payment-api, and verify HTTP 200 on /process-payment."
    )
    expected_tools = ["tail", "grep", "curl", "vim/nano", "systemctl"]
    investigation_guidance = (
        "Inspect the application log with 'tail -n 30 /var/log/app/payment.log'. "
        "Notice the error: 'Connection refused to database at 127.0.0.1:5433'. "
        "Inspect '/etc/app/payment.conf'. Notice 'db_port': 5433 instead of 5432. "
        "Update the port to 5432, restart payment-api, and test with curl."
    )
    hints = [
        "Check recent stack traces in '/var/log/app/payment.log' using 'tail -n 30'.",
        "Notice the database port reported in the error message is 5433 instead of standard 5432. Check '/etc/app/payment.conf'.",
        "Change 'db_port': 5433 to 'db_port': 5432 in '/etc/app/payment.conf' and run 'systemctl restart payment-api'.",
    ]
    expected_root_cause = (
        "In '/etc/app/payment.conf', 'db_port' was set to 5433 instead of 5432, "
        "causing the Payment API to throw DatabaseConnectionError on every checkout request."
    )
    expected_fix = (
        "Inspected /var/log/app/payment.log, identified the invalid port 5433, "
        "corrected 'db_port': 5432 in '/etc/app/payment.conf', and restarted payment-api."
    )
    validation = "Confirm 'curl -s http://localhost:8000/process-payment' returns HTTP 200 with status 'success'."
    learning_points = [
        "Analyzing application log stack traces to differentiate host vs port vs auth errors",
        "Correlating microservice config parameters with downstream dependency ports",
        "Testing transactional endpoints using curl with HTTP status code validation",
    ]
    postmortem_sections = {
        "methodology": "Reproduced transaction failure -> Examined /var/log/app/payment.log -> Found port 5433 -> Checked config -> Fixed port to 5432 -> Re-tested transaction.",
        "evidence": "Log entry: 'DatabaseConnectionError: Connection refused to database at 127.0.0.1:5433'.",
        "root_cause": "Configuration value db_port was typoed as 5433.",
        "remediation": "Updated db_port to 5432 in /etc/app/payment.conf and restarted payment-api.",
        "validation_steps": "Invoked curl http://localhost:8000/process-payment; received HTTP 200 success."
    }

    def setup(self, controller: LabController) -> bool:
        conf = '{"port": 8000, "db_host": "unreachable.internal", "db_port": 5433, "timeout": 3}'
        controller.exec_cmd(f"cat << 'EOF' | sudo tee /etc/app/payment.conf > /dev/null\n{conf}\nEOF")
        controller.exec_cmd("systemctl restart payment-api")
        # Trigger failed transaction so log is written
        controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        code, out, _ = controller.exec_cmd("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/process-payment")
        return out.strip() == "500"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        if "success" not in out:
            return False, f"Payment API transaction is still failing: {out.strip()}", {"response": out.strip()}

        return True, "Database port configuration corrected and payment transactions succeeding.", {"status": "healthy"}
