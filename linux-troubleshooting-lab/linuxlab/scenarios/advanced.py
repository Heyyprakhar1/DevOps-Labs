import time
from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class DualLayerDNSFailureScenario(Scenario):
    """Scenario: Both /etc/hosts and payment.conf have poisoned/invalid mappings."""

    id = "adv_001"
    category = "networking"
    level = "ADVANCED"
    difficulty = "ADVANCED"
    title = "Cascading Dual-Layer Resolution Failure Across Microservices"
    symptoms = [
        "Payment transactions failing with HTTP 500 across all clients",
        "Stack traces show alternating hostname resolution failures and connection refused",
        "Multiple dependency endpoints unreachable from prod-app-server-01",
    ]
    context = (
        "An incident commander escalated a multi-signal networking failure: "
        "The checkout system cannot process payments. During an earlier emergency rollback, "
        "an engineer modified both /etc/hosts AND /etc/app/payment.conf, leaving contradictory records. "
        "Diagnose both layers, reconcile the database destination, and restore transaction processing."
    )
    objective = (
        "1. Identify the multiple conflicting resolution configurations.\n"
        "2. Correct /etc/hosts and /etc/app/payment.conf to route database traffic to 127.0.0.1.\n"
        "3. Restart payment-api and verify successful transactions via curl."
    )
    expected_tools = ["tail", "grep", "getent", "curl", "vim/nano", "systemctl"]
    investigation_guidance = (
        "Check /var/log/app/payment.log to see the failure. "
        "Inspect /etc/app/payment.conf. Notice 'db_host' is set to 'unreachable.internal'. "
        "Inspect /etc/hosts. Notice 'db.internal' is mapped to '127.0.0.99'. "
        "Update /etc/app/payment.conf to use '127.0.0.1' (or map the hostname in /etc/hosts to 127.0.0.1), "
        "restart payment-api, and test with curl."
    )
    hints = [
        "Notice that resolving the hostname fails across two separate layers: the config file and the host resolver.",
        "Check both '/etc/app/payment.conf' (db_host parameter) and '/etc/hosts' for erroneous IP mappings.",
        "Set 'db_host': '127.0.0.1' in '/etc/app/payment.conf' (or point the hostname in '/etc/hosts' to 127.0.0.1), and restart payment-api.",
    ]
    expected_root_cause = (
        "A dual-layer configuration failure: '/etc/app/payment.conf' referenced an invalid host 'unreachable.internal' "
        "while '/etc/hosts' blackholed 'db.internal' to '127.0.0.99', preventing database connection establishment."
    )
    expected_fix = (
        "Reconciled both resolution layers by setting 'db_host': '127.0.0.1' in '/etc/app/payment.conf' "
        "(and removing the blackhole mapping from /etc/hosts), then restarted payment-api."
    )
    validation = "Confirm 'curl -s http://localhost:8000/process-payment' returns HTTP 200 with status 'success'."
    learning_points = [
        "Multi-layer troubleshooting: isolating application config vs OS resolver vs DNS",
        "How getaddrinfo traverses /etc/nsswitch.conf and /etc/hosts",
        "Validating downstream service health after partial deployments",
    ]
    postmortem_sections = {
        "signal_correlation": "Application log showed connection failures across both hostname lookup and socket connect phases.",
        "eliminated_hypotheses": "Ruled out network interface failure (loopback was up) and payment-api process crash (daemon was active).",
        "root_cause": "Dual-layer host resolution drift between application configuration and host /etc/hosts.",
        "blast_radius": "Complete checkout transaction outage (100% transaction failure rate).",
        "remediation": "Standardized database connection host to localhost in application config and restarted service."
    }

    def setup(self, controller: LabController) -> bool:
        # Poison /etc/hosts
        controller.exec_cmd("grep -v 'db.internal' /etc/hosts | sudo tee /etc/hosts > /dev/null")
        controller.exec_cmd("echo '127.0.0.99 db.internal # linuxlab-injected' | sudo tee -a /etc/hosts")
        # Poison payment.conf
        conf = '{"port": 8000, "db_host": "unreachable.internal", "db_port": 5432, "timeout": 3}'
        controller.exec_cmd(f"cat << 'EOF' | sudo tee /etc/app/payment.conf > /dev/null\n{conf}\nEOF")
        controller.exec_cmd("systemctl restart payment-api")
        controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        code, out, _ = controller.exec_cmd("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/process-payment")
        return out.strip() == "500"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        if "success" not in out:
            return False, f"Payment API transaction is still failing: {out.strip()}", {"response": out.strip()}

        return True, "Cascading resolution failure resolved and payment transactions succeeding.", {"status": "healthy"}


class ReadOnlyMountScenario(Scenario):
    """Scenario: A filesystem mount was remounted read-only, degrading writes."""

    id = "adv_002"
    category = "disk"
    level = "ADVANCED"
    difficulty = "ADVANCED"
    title = "Silent Read-Only Mount Degrading Cache Subsystem"
    symptoms = [
        "Web applications throwing 'Read-only file system' (EROFS / Errno 30)",
        "df -h reports 80% free disk space",
        "df -i reports 95% free inodes",
    ]
    context = (
        "Application telemetry reports sporadic 500 errors when writing temporary cache buffers. "
        "The infrastructure dashboard displays plenty of free disk blocks and inodes. "
        "Yet any attempts to create or modify files in /var/spool/app_cache fail with: "
        "'OSError: [Errno 30] Read-only file system'. Investigate the mount status and restore write capability."
    )
    objective = (
        "1. Identify why writes to /var/spool/app_cache are rejected despite ample disk space and inodes.\n"
        "2. Inspect mount options in /proc/mounts or mount output.\n"
        "3. Remount the filesystem with read-write permissions (mount -o remount,rw) and verify file creation."
    )
    expected_tools = ["mount", "cat /proc/mounts", "touch", "sudo"]
    investigation_guidance = (
        "Inspect the mount options for /var/spool/app_cache using 'cat /proc/mounts' or 'mount | grep app_cache'. "
        "Notice the 'ro' (read-only) mount option. "
        "Remount the filesystem in read-write mode using 'sudo mount -o remount,rw /var/spool/app_cache'. "
        "Verify you can create files with 'touch /var/spool/app_cache/test.tmp'."
    )
    hints = [
        "The error is Errno 30 (EROFS). Check filesystem mount options rather than block or inode capacity.",
        "Run 'mount | grep app_cache' or 'cat /proc/mounts | grep app_cache'. Look for 'ro' vs 'rw'.",
        "Remount the directory as read-write with 'sudo mount -o remount,rw /var/spool/app_cache'.",
    ]
    expected_root_cause = (
        "The '/var/spool/app_cache' tmpfs filesystem was remounted read-only (ro), "
        "causing the kernel to reject all file creation and modification syscalls with EROFS."
    )
    expected_fix = (
        "Identified the 'ro' flag in /proc/mounts, executed 'sudo mount -o remount,rw /var/spool/app_cache', "
        "and confirmed write functionality."
    )
    validation = "Confirm 'touch /var/spool/app_cache/verify.tmp' succeeds and /proc/mounts shows 'rw'."
    learning_points = [
        "Distinguishing between capacity exhaustion (ENOSPC) and write protection (EROFS)",
        "How Linux remounts filesystems read-only upon I/O errors or maintenance flags",
        "Using mount -o remount,rw to restore operational state without unmounting active targets",
    ]
    postmortem_sections = {
        "signal_correlation": "Error Errno 30 was initially suspected to be a disk full condition, but df -h and df -i ruled out capacity exhaustion.",
        "eliminated_hypotheses": "Ruled out block exhaustion (df -h had 80% free), inode exhaustion (df -i had 95% free), and file permissions (directory was 777).",
        "root_cause": "Filesystem mount option 'ro' prohibited all kernel VFS write operations.",
        "blast_radius": "Cache and session write operations failed for all incoming application requests.",
        "remediation": "Remounted the target filesystem with 'mount -o remount,rw'."
    }

    def setup(self, controller: LabController) -> bool:
        # Ensure mount exists
        controller.exec_cmd(
            "mountpoint -q /var/spool/app_cache || "
            "sudo mount -t tmpfs -o size=20M tmpfs /var/spool/app_cache"
        )
        # Remount as read-only
        controller.exec_cmd("sudo mount -o remount,ro /var/spool/app_cache")
        # Verify touch fails
        code, _, err = controller.exec_cmd("touch /var/spool/app_cache/test.tmp 2>&1")
        return code != 0 or "Read-only" in err

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Verify file creation succeeds
        code, _, err = controller.exec_cmd(
            "touch /var/spool/app_cache/verify.tmp && rm -f /var/spool/app_cache/verify.tmp",
            user="devops"
        )
        if code != 0:
            return False, f"Cannot write to /var/spool/app_cache: {err}", {"creatable": False}

        return True, "Filesystem remounted read-write and cache operations restored.", {"status": "healthy"}


class MultiLayerRegressionScenario(Scenario):
    """Scenario: Permissions stripped on config AND port occupied by rogue process."""

    id = "adv_003"
    category = "services"
    level = "ADVANCED"
    difficulty = "ADVANCED"
    title = "Multi-Layered Regression: Permissions Stripped and Port Collision"
    symptoms = [
        "Web application service crashed and fails to restart",
        "First attempt to start fails with PermissionError",
        "Subsequent start attempt after fixing permissions fails with 'Address already in use'",
    ]
    context = (
        "An emergency patch deployment triggered multiple overlapping regressions. "
        "web-app.service will not start. The first diagnostic check reveals a file permissions issue. "
        "However, resolving the first issue exposes an underlying second failure layer. "
        "Investigate both failure points, systematically resolve them, and restore web-app.service."
    )
    objective = (
        "1. Identify and resolve the restrictive permissions on /etc/app/web_app.conf.\n"
        "2. Identify and terminate the rogue process occupying port 8080.\n"
        "3. Start web-app.service and verify HTTP 200 on port 8080."
    )
    expected_tools = ["systemctl", "journalctl", "chmod", "ss", "lsof", "kill"]
    investigation_guidance = (
        "Check 'systemctl status web-app'. Notice PermissionError on '/etc/app/web_app.conf'. "
        "Fix permissions with 'sudo chmod 644 /etc/app/web_app.conf'. "
        "Attempting to start the service now exposes a second error: 'Address already in use'. "
        "Check port 8080 with 'ss -tulpn | grep 8080' or 'lsof -i :8080'. "
        "Terminate the rogue process holding port 8080, then restart web-app."
    )
    hints = [
        "This incident has two distinct failure layers. Fix the first error reported in journalctl, then inspect the new error that appears.",
        "Layer 1 is file permissions on '/etc/app/web_app.conf' (chmod 644). Layer 2 is a port conflict on port 8080.",
        "Run 'sudo chmod 644 /etc/app/web_app.conf', kill the rogue process on port 8080 with 'pkill -9 -f rogue_listener', and run 'systemctl restart web-app'.",
    ]
    expected_root_cause = (
        "Two concurrent regressions: '/etc/app/web_app.conf' had permissions set to 000, "
        "and an orphaned netcat process occupied port 8080, causing sequential startup failures."
    )
    expected_fix = (
        "Restored config permissions via 'sudo chmod 644 /etc/app/web_app.conf', "
        "terminated the rogue listener via 'kill <PID>', and restarted web-app."
    )
    validation = "Confirm 'systemctl is-active web-app' returns active and 'curl http://localhost:8080/health' returns UP."
    learning_points = [
        "Handling multi-layered production incidents without premature conclusion after resolving first symptom",
        "Reading iterative failure logs across sequential restart attempts",
        "Clean process hygiene to prevent orphaned listeners during failed deployments",
    ]
    postmortem_sections = {
        "signal_correlation": "Iterative diagnostic signals: PermissionError on config read followed by EADDRINUSE on socket bind.",
        "eliminated_hypotheses": "Correcting permissions proved necessary but not sufficient; socket inspection was required.",
        "root_cause": "Dual regression: stripped configuration permissions masked an underlying socket collision.",
        "blast_radius": "Web service remained completely unavailable throughout both stages.",
        "remediation": "Sequentially restored read permissions and terminated conflicting socket owner."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd("systemctl stop web-app")
        # Strip permissions on config
        controller.exec_cmd("sudo chmod 000 /etc/app/web_app.conf")
        # Spawn rogue listener on port 8080
        cmd = "nohup bash -c 'exec -a rogue_listener nc -l -k -p 8080' > /dev/null 2>&1 &"
        controller.exec_cmd(cmd, user="devops")
        time.sleep(1)
        # Attempt start
        controller.exec_cmd("systemctl start web-app")
        code, out, _ = controller.exec_cmd("systemctl is-active web-app")
        return code != 0 or out.strip() != "active"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check permissions
        _, mode_out, _ = controller.exec_cmd("stat -c '%a' /etc/app/web_app.conf")
        if mode_out.strip() in ["0", "000", "200"]:
            return False, "Permissions on /etc/app/web_app.conf are still restrictive.", {"mode": mode_out.strip()}

        # Check rogue listener
        code, out, _ = controller.exec_cmd("pgrep -f rogue_listener")
        if code == 0 and out.strip():
            return False, "Rogue listener on port 8080 is still active.", {"rogue_pid": out.strip()}

        # Check web-app is active
        s_code, s_out, _ = controller.exec_cmd("systemctl is-active web-app")
        if s_code != 0 or s_out.strip() != "active":
            return False, "web-app.service is not running. Did you restart the service?", {"active": False}

        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "web-app is active but health check failed.", {"health": False}

        return True, "Both permissions and port conflict resolved; web-app is running healthy.", {"status": "healthy"}


class ZombieProcessFloodScenario(Scenario):
    """Scenario: Runaway fork process creating hundreds of defunct zombie processes."""

    id = "adv_004"
    category = "processes"
    level = "ADVANCED"
    difficulty = "ADVANCED"
    title = "Orphaned Zombie Flood Saturating Process Namespace"
    symptoms = [
        "Process table inspection reveals numerous '<defunct>' processes",
        "Attempts to kill defunct processes with 'kill -9' have no effect",
        "Risk of PID allocation exhaustion on host",
    ]
    context = (
        "Monitoring detected a rapid spike in process count on prod-app-server-01. "
        "Running 'ps aux' shows dozens of '<defunct>' zombie tasks. "
        "A junior engineer tried executing 'kill -9' on the zombie PIDs, but they remain. "
        "Diagnose why the zombies persist, locate the root parent process that is failing to reap them, "
        "terminate the parent, and clear the zombie flood."
    )
    objective = (
        "1. Understand why defunct/zombie processes cannot be killed directly.\n"
        "2. Identify the parent PID (PPID) responsible for forking and abandoning child processes.\n"
        "3. Terminate the parent process ('zombie_spawner') so the zombie chain is reaped."
    )
    expected_tools = ["ps", "pstree", "top", "kill"]
    investigation_guidance = (
        "Remember: A zombie process is already dead; it remains in the process table because "
        "its parent has not called wait() or waitpid(). "
        "Find the parent PID using 'ps -eo pid,ppid,stat,comm | grep -w Z'. "
        "Look up the parent process command using 'ps -p <PPID> -o pid,comm,args'. "
        "Terminate the parent process with 'kill -9 <PPID>'."
    )
    hints = [
        "Zombie processes (stat 'Z') are already terminated and cannot receive signals. You must kill their parent process.",
        "Inspect the PPID (parent process ID) of the zombies using 'ps -eo pid,ppid,stat,args | grep -w Z'.",
        "Find the PID of 'zombie_spawner' and terminate it with 'kill -9 <PPID>' (or 'pkill -9 -f zombie_spawner').",
    ]
    expected_root_cause = (
        "A rogue parent process ('zombie_spawner') continuously forked child processes "
        "and failed to call waitpid(), causing dead children to remain as <defunct> zombies in the process table."
    )
    expected_fix = (
        "Identified the parent process ID (PPID) via 'ps -eo pid,ppid,stat,args', "
        "terminated the parent process using 'kill -9 <PPID>', allowing the init process to reap the zombie children."
    )
    validation = "Confirm 'ps -eo stat | grep -c Z' returns 0 and 'pgrep -f zombie_spawner' is empty."
    learning_points = [
        "Linux process lifecycle: fork(), exit(), wait(), and zombie state",
        "Why kill -9 on zombie processes fails (they have no execution context to receive signals)",
        "How terminating an unresponsive parent causes orphans to be reparented to init (PID 1) and reaped",
    ]
    postmortem_sections = {
        "signal_correlation": "High process count was driven not by active CPU consumers but by un-reaped dead task entries in the kernel process table.",
        "eliminated_hypotheses": "Ruled out active CPU hog (zombies consume 0% CPU); direct signal delivery to zombies was confirmed ineffective.",
        "root_cause": "Buggy parent daemon omitted waitpid() reaping loop.",
        "blast_radius": "Process ID (PID) table exhaustion threatening kernel task allocation.",
        "remediation": "Terminated parent process via SIGKILL; kernel re-parented and reaped all defunct children."
    }

    def setup(self, controller: LabController) -> bool:
        cmd = (
            "nohup bash -c 'exec -a zombie_spawner python3 -c \""
            "import os, time\n"
            "for _ in range(25):\n"
            "    if os.fork() == 0:\n"
            "        os._exit(0)\n"
            "time.sleep(7200)\n"
            "\"' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(cmd, user="devops")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("pgrep -f zombie_spawner")
        return code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("pgrep -f zombie_spawner")
        if code == 0 and out.strip():
            return False, f"Parent process 'zombie_spawner' is still active with PID {out.strip()}.", {"parent_pid": out.strip()}

        return True, "Parent process terminated and zombie processes successfully reaped.", {"status": "healthy"}


class StealthMemoryLeakScenario(Scenario):
    """Scenario: A stealth background daemon progressively eating memory."""

    id = "adv_005"
    category = "memory"
    level = "ADVANCED"
    difficulty = "ADVANCED"
    title = "Stealth Memory Leak Starving Application Buffers"
    symptoms = [
        "Available memory fluctuating critically low (<100MB)",
        "Application worker response times spiking by 300%",
        "Kernel buffer allocation warnings logged in dmesg",
    ]
    context = (
        "Telemetry indicates that prod-app-server-01 is under severe memory distress. "
        "Available memory has dropped below 100MB, leaving no room for filesystem cache or worker buffers. "
        "A background telemetry agent ('buffer_leak') was introduced recently. "
        "Analyze the resident memory distribution, track down the leaking daemon, terminate it, and restore memory headroom."
    )
    objective = (
        "1. Inspect memory consumption using free, vmstat, and ps.\n"
        "2. Identify the process consuming excessive resident set size (RSS).\n"
        "3. Terminate 'buffer_leak' and verify available RAM recovers above 400MB."
    )
    expected_tools = ["free", "vmstat", "ps", "top", "kill"]
    investigation_guidance = (
        "Inspect memory with 'free -m'. Notice available memory is very low. "
        "Run 'ps -eo pid,user,%mem,rss,comm,args --sort=-rss | head -n 10' or 'top' (Shift+M). "
        "Locate the background process named 'buffer_leak' holding >350MB of memory. "
        "Terminate it with 'kill -9 <PID>' and verify available RAM with 'free -m'."
    )
    hints = [
        "Check overall available memory using 'free -m' or 'free -h'.",
        "Identify high RSS consumers by sorting processes with 'ps aux --sort=-%mem | head -n 10'.",
        "Terminate the leaking daemon 'buffer_leak' using 'pkill -9 -f buffer_leak' (or kill <PID>).",
    ]
    expected_root_cause = (
        "A background telemetry script ('buffer_leak') held an unbounded memory buffer of >350MB, "
        "exhausting host memory headroom and forcing the kernel to drop page cache."
    )
    expected_fix = (
        "Identified the memory leak via 'ps aux --sort=-%mem', terminated the process via 'kill -9 <PID>', "
        "and verified memory recovery with 'free -m'."
    )
    validation = "Confirm 'free -m' shows available memory > 400MB and 'pgrep -f buffer_leak' is empty."
    learning_points = [
        "Interpreting RSS (Resident Set Size) vs VSZ (Virtual Size) in process diagnostics",
        "How memory pressure degrades performance by evicting OS page cache",
        "Using continuous sampling with vmstat 1 3 to track memory trajectory",
    ]
    postmortem_sections = {
        "signal_correlation": "Application latency regression correlated directly with kernel page cache eviction caused by resident memory starvation.",
        "eliminated_hypotheses": "Ruled out disk space saturation (df was normal) and high CPU load (CPU load was low).",
        "root_cause": "Unbounded memory buffer accumulation inside telemetry collection daemon.",
        "blast_radius": "System-wide I/O degradation and impending OOM killer activation.",
        "remediation": "Terminated culprit process and restored 400MB+ available memory buffer."
    }

    def setup(self, controller: LabController) -> bool:
        cmd = (
            "nohup bash -c 'exec -a buffer_leak python3 -c \""
            "import time\n"
            "buf = bytearray(360 * 1024 * 1024)\n"
            "time.sleep(7200)\n"
            "\"' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(cmd, user="devops")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("pgrep -f buffer_leak")
        return code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("pgrep -f buffer_leak")
        if code == 0 and out.strip():
            return False, f"Leaking process 'buffer_leak' is still running with PID {out.strip()}.", {"pid": out.strip()}

        return True, "Memory leak terminated and memory headroom restored.", {"status": "healthy"}
