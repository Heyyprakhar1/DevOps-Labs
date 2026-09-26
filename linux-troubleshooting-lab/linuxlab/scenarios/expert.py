import time
from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class ProductionOutageNetworkScenario(Scenario):
    """Scenario: P1 Production incident with ambiguous downstream routing failure."""

    id = "expert_001"
    category = "networking"
    level = "EXPERT"
    difficulty = "EXPERT"
    title = "P1 Outage: Intermittent Downstream Timeout with Phantom Gateway Failures"
    symptoms = [
        "PagerDuty P1 High-Severity Outage: Customer checkout transaction failure rate > 80%",
        "Frontend web services report HTTP 500/504 errors on checkout submission",
        "No application deployments recorded in git history over the last 24 hours",
    ]
    context = (
        "Incident Commander Briefing: Production monitoring generated a P1 page. "
        "End users cannot complete checkouts on prod-app-server-01. "
        "The web-app service appears healthy, but transactions directed to the payment API "
        "(http://localhost:8000/process-payment) fail with internal server errors. "
        "No application deployments occurred. Formulate hypotheses, collect host evidence, "
        "isolate the root cause, remediate the failure, and validate recovery."
    )
    objective = (
        "1. Formulate hypotheses covering application, networking, host resolver, and socket layers.\n"
        "2. Collect diagnostic evidence from logs, network sockets, and system configuration.\n"
        "3. Eliminate false leads, restore connectivity to 127.0.0.1, and validate HTTP 200 on /process-payment."
    )
    expected_tools = ["curl", "tail", "grep", "ss", "getent", "vim/nano", "systemctl"]
    investigation_guidance = (
        "Approach this as a Senior SRE: Check the entrypoint (curl payment-api /process-payment), "
        "inspect /var/log/app/payment.log for stack traces, inspect how host resolution maps db.internal "
        "via /etc/hosts, correct any routing or configuration anomalies, and validate end-to-end checkout."
    )
    hints = [
        "Examine the failure from the application's perspective: where does the transaction log report the request stalled?",
        "Trace host resolution and downstream connectivity from inside the payment service.",
        "Verify whether db.internal maps to a reachable IP in /etc/hosts or /etc/app/payment.conf.",
    ]
    expected_root_cause = (
        "A blackholed destination record in '/etc/hosts' routed 'db.internal' to non-routable address '127.0.0.99', "
        "causing downstream database calls to fail with ConnectionRefusedError during transaction processing."
    )
    expected_fix = (
        "Diagnosed database connection timeout in /var/log/app/payment.log, updated /etc/hosts "
        "to map 'db.internal' to '127.0.0.1', and verified end-to-end checkout with curl."
    )
    validation = "Confirm 'curl -s http://localhost:8000/process-payment' returns HTTP 200 with status 'success'."
    learning_points = [
        "SRE Incident Command: Hypothesis formation, progressive elimination, and evidence logging",
        "Understanding host-level name resolution order (/etc/nsswitch.conf -> /etc/hosts -> DNS)",
        "Differentiating between local service failure and downstream dependency degradation",
    ]
    postmortem_sections = {
        "incident_summary": "P1 customer-facing outage where checkout transactions failed with HTTP 500 due to blackholed database routing.",
        "impact": "100% of checkout payment requests failed during the incident window.",
        "detection": "Automated Prometheus alert 'PaymentGatewayFailureRateHigh' triggered at 04:12 UTC.",
        "initial_hypotheses": "1. Payment API crash; 2. Saturated TCP connection backlog; 3. Downstream host resolution failure; 4. Out-of-memory worker termination.",
        "evidence_collected": "/var/log/app/payment.log showed DatabaseConnectionError to db.internal:5432. /etc/hosts mapped db.internal to 127.0.0.99.",
        "root_cause": "An unverified network host configuration in /etc/hosts mapped the database hostname to a non-existent loopback IP.",
        "contributing_factors": "Absence of integration canary tests before live configuration updates.",
        "remediation": "Updated /etc/hosts mapping db.internal to 127.0.0.1 and restarted payment-api.",
        "validation": "Invoked test payment transaction via curl; confirmed HTTP 200 and valid transaction ID.",
        "prevention": "Implement DNS service discovery with health-checking rather than hardcoded /etc/hosts entries."
    }

    def setup(self, controller: LabController) -> bool:
        # Route db.internal in payment.conf and blackhole in /etc/hosts
        conf = '{"port": 8000, "db_host": "db.internal", "db_port": 5432, "timeout": 3}'
        controller.exec_cmd(f"cat << 'EOF' | sudo tee /etc/app/payment.conf > /dev/null\n{conf}\nEOF")
        controller.exec_cmd("grep -v 'db.internal' /etc/hosts | sudo tee /etc/hosts > /dev/null")
        controller.exec_cmd("echo '127.0.0.99 db.internal # linuxlab-injected' | sudo tee -a /etc/hosts")
        controller.exec_cmd("systemctl restart payment-api")
        controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        code, out, _ = controller.exec_cmd("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/process-payment")
        return out.strip() == "500"

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, out, _ = controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        if "success" not in out:
            return False, f"Transactions are still failing: {out.strip()}", {"response": out.strip()}

        return True, "Production network incident resolved and payments processing successfully.", {"status": "healthy"}


class MultiServiceDeadlockScenario(Scenario):
    """Scenario: Catastrophic aborted deployment leaving multiple services deadlocked."""

    id = "expert_002"
    category = "services"
    level = "EXPERT"
    difficulty = "EXPERT"
    title = "Catastrophic Rollout Abort: Multi-Service Deadlock and Corrupted State"
    symptoms = [
        "Complete platform failure: both web-app and payment-api are down",
        "Automated deployment pipeline aborted mid-execution with non-zero exit code",
        "Executive escalation: P0 outage affecting all production services",
    ]
    context = (
        "Incident Commander Briefing: An automated canary rollout crashed halfway through step 4 of 7. "
        "The host prod-app-server-01 was left in an aborted, inconsistent state: "
        "web-app fails to start due to configuration syntax corruption, a rogue process holds port 8080, "
        "and payment-api cannot start because of an invalid port configuration. "
        "Systematically triage the host, isolate each subsystem, eliminate each roadblock, and recover full operations."
    )
    objective = (
        "1. Triage web-app.service: repair /etc/app/web_app.conf and terminate rogue listener on port 8080.\n"
        "2. Triage payment-api.service: correct port configuration in /etc/app/payment.conf.\n"
        "3. Bring both services online and verify both /health endpoints and transactional workflow."
    )
    expected_tools = ["systemctl", "journalctl", "ss", "lsof", "jq", "kill", "curl"]
    investigation_guidance = (
        "Triage one service at a time. "
        "For web-app: inspect 'journalctl -u web-app', repair invalid JSON in '/etc/app/web_app.conf', "
        "check if port 8080 is blocked via 'ss -tulpn', terminate rogue listener, and restart web-app. "
        "For payment-api: inspect '/etc/app/payment.conf', ensure port is 8000 and db_host is reachable, "
        "restart payment-api, and verify both endpoints."
    )
    hints = [
        "Triage the services independently. What is preventing web-app from running? What is preventing payment-api?",
        "Check both /etc/app/web_app.conf (JSON syntax) and port 8080 (rogue listener). Check /etc/app/payment.conf (port 8000).",
        "Fix the JSON in web_app.conf, kill the netcat rogue listener on 8080, set port 8000 in payment.conf, and restart both services.",
    ]
    expected_root_cause = (
        "An aborted deployment script left corrupt JSON in '/etc/app/web_app.conf', "
        "an orphaned netcat process bound to port 8080, and an invalid port (8005) in '/etc/app/payment.conf'."
    )
    expected_fix = (
        "Repaired JSON syntax in web_app.conf, killed rogue listener occupying port 8080, "
        "corrected port to 8000 in payment.conf, and restarted both services."
    )
    validation = "Confirm 'curl http://localhost:8080/health' and 'curl http://localhost:8000/health' both return UP."
    learning_points = [
        "Managing multi-fault cascading outages under incident pressure",
        "Decoupling interdependent services during emergency triage",
        "Validating atomic deployment rollbacks vs partial manual intervention",
    ]
    postmortem_sections = {
        "incident_summary": "P0 total system failure triggered by mid-deployment crash that left services in inconsistent states.",
        "impact": "100% loss of both front-end web portal and back-end payment processing capabilities.",
        "detection": "Deployment pipeline health-check failure followed by PagerDuty Sev-0 notification.",
        "initial_hypotheses": "1. Host hardware degradation; 2. Corrupted system packages; 3. Incomplete file updates from aborted deploy script.",
        "evidence_collected": "web_app.conf had truncated JSON syntax; ss showed orphaned netcat on 8080; payment.conf had drifted port 8005.",
        "root_cause": "The deploy pipeline lacked transactional rollback; failing steps left half-applied file writes.",
        "contributing_factors": "Absence of pre-validation linters in deployment agent scripts.",
        "remediation": "Sequentially fixed web-app configuration, cleared port collision, fixed payment config, restarted all units.",
        "validation": "Both services active and responding with HTTP 200; live checkout verification succeeded.",
        "prevention": "Migrate deployments to blue-green or atomic symlink swapping to guarantee all-or-nothing rollouts."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd("systemctl stop web-app")
        controller.exec_cmd("systemctl stop payment-api")
        # Corrupt web_app.conf
        controller.exec_cmd("cat << 'EOF' > /etc/app/web_app.conf\n{\n  \"port\": 8080,\n  CORRUPT_DEPLOYMENT_TOKEN\n}\nEOF")
        # Occupy port 8080
        controller.exec_cmd("nohup bash -c 'exec -a rogue_listener nc -l -k -p 8080' > /dev/null 2>&1 &")
        # Corrupt payment.conf port
        controller.exec_cmd("cat << 'EOF' | sudo tee /etc/app/payment.conf > /dev/null\n{\"port\": 8005, \"db_host\": \"127.0.0.1\", \"db_port\": 5432, \"timeout\": 3}\nEOF")
        controller.exec_cmd("systemctl start web-app")
        controller.exec_cmd("systemctl start payment-api")
        time.sleep(1)
        w_code, _, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        p_code, _, _ = controller.exec_cmd("curl -s http://localhost:8000/health")
        return w_code != 0 and p_code != 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check web-app
        w_code, w_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if w_code != 0 or "UP" not in w_out:
            return False, "web-app is not responding with HTTP 200 on port 8080.", {"web_app": "down"}

        # Check payment-api
        p_code, p_out, _ = controller.exec_cmd("curl -s http://localhost:8000/health")
        if p_code != 0 or "UP" not in p_out:
            return False, "payment-api is not responding with HTTP 200 on port 8000.", {"payment_api": "down"}

        # Check payment transaction
        t_code, t_out, _ = controller.exec_cmd("curl -s http://localhost:8000/process-payment")
        if "success" not in t_out:
            return False, "payment-api is up but transaction processing failed.", {"transaction": "fail"}

        return True, "Multi-service deadlock fully resolved; all services operational.", {"status": "healthy"}


class ShadowedStorageExhaustionScenario(Scenario):
    """Scenario: Open unlinked files combined with unrotated transaction logs consuming storage."""

    id = "expert_003"
    category = "disk"
    level = "EXPERT"
    difficulty = "EXPERT"
    title = "Silent Disk Full: Shadowed File Descriptors and Unlinked Storage Ingestion"
    symptoms = [
        "System alerts: /var/log volume critically full (>95%)",
        "Applications unable to append to transaction logs or write state",
        "Directory inspection with 'du' accounts for only a fraction of used space",
    ]
    context = (
        "Incident Commander Briefing: Critical transaction logging has halted across prod-app-server-01. "
        "The monitoring agent reports disk space is 98% full. "
        "A sysadmin checked /var/log and deleted an apparent archive file, but the disk usage remained saturated. "
        "Furthermore, a bloated transaction log continues to grow. "
        "Conduct a comprehensive filesystem investigation, uncover all sources of block consumption, and reclaim capacity."
    )
    objective = (
        "1. Identify the unlinked open file descriptor withholding disk blocks using lsof.\n"
        "2. Identify the bloated on-disk log file in /var/log/app/.\n"
        "3. Safely reclaim disk capacity from both sources and verify filesystem recovery."
    )
    expected_tools = ["df", "du", "lsof", "find", "kill", "head"]
    investigation_guidance = (
        "Run 'df -h' to see total usage. Use 'lsof +L1' or 'lsof | grep deleted' to detect the unlinked "
        "process 'shadow_writer' holding ~250MB of space, and terminate it. "
        "Next, find on-disk log bloat using 'du -sh /var/log/app/*' or 'find /var/log -type f -size +100M', "
        "and truncate '/var/log/app/transaction.log' using '> /var/log/app/transaction.log'."
    )
    hints = [
        "Space is being consumed across two distinct vectors: an unlinked open descriptor AND an oversized on-disk file.",
        "Use 'lsof +L1' to find unlinked files held by running processes. Use 'find /var/log -size +50M' for on-disk bloat.",
        "Kill the process holding the deleted file with 'pkill -9 -f shadow_writer' and truncate '/var/log/app/transaction.log'.",
    ]
    expected_root_cause = (
        "Dual storage exhaustion: a background worker ('shadow_writer') held an open descriptor to a deleted 250MB file, "
        "while an unrotated transaction log ('transaction.log') consumed an additional 200MB on disk."
    )
    expected_fix = (
        "Terminated 'shadow_writer' via 'kill <PID>' to release unlinked blocks, "
        "and truncated '/var/log/app/transaction.log' with '> /var/log/app/transaction.log'."
    )
    validation = "Confirm 'df -h' reports ample free space and touch in /var/log/app succeeds."
    learning_points = [
        "Comprehensive storage triage combining superblock state (df), directory tree (du), and file tables (lsof)",
        "Why partial remediation leaves production hosts vulnerable to immediate recurrence",
        "Implementing production log rotation and inode monitoring policies",
    ]
    postmortem_sections = {
        "incident_summary": "Storage exhaustion outage caused by simultaneous unlinked descriptor leak and unrotated on-disk logs.",
        "impact": "Application unable to persist transaction state; transaction error rate reached 100%.",
        "detection": "Prometheus disk utilization alert 'FilesystemUsageCritical' at 95% threshold.",
        "initial_hypotheses": "1. Large temporary dump file; 2. Core dump accumulation; 3. Active open file descriptor holding unlinked inode.",
        "evidence_collected": "lsof revealed shadow_writer holding a deleted 250MB inode; du identified 200MB transaction.log.",
        "root_cause": "Uncoordinated log deletion failed to close the active file handle; debug logging filled transaction.log.",
        "contributing_factors": "Lack of automated logrotate configuration on application log paths.",
        "remediation": "Terminated holding process and truncated active transaction log.",
        "validation": "df -h verified >500MB free capacity; write probes succeeded.",
        "prevention": "Deploy standard logrotate configuration with copytruncate directives."
    }

    def setup(self, controller: LabController) -> bool:
        # Create unlinked open file (250MB)
        cmd = (
            "nohup bash -c 'exec -a shadow_writer python3 -c \""
            "import os, time\n"
            "p = \\\"/var/log/app/shadow.log\\\"\n"
            "with open(p, \\\"wb\\\") as f:\n"
            "    f.write(b\\\"Z\\\" * (250 * 1024 * 1024))\n"
            "    f.flush()\n"
            "    os.unlink(p)\n"
            "    time.sleep(7200)\n"
            "\"' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(cmd, user="devops")
        # Create on-disk bloated log (200MB)
        controller.exec_cmd("fallocate -l 200M /var/log/app/transaction.log 2>/dev/null || dd if=/dev/zero of=/var/log/app/transaction.log bs=1M count=200 2>/dev/null")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("pgrep -f shadow_writer")
        return code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check shadow_writer
        code, out, _ = controller.exec_cmd("pgrep -f shadow_writer")
        if code == 0 and out.strip():
            return False, "Process 'shadow_writer' is still holding the open unlinked file descriptor.", {"pid": out.strip()}

        # Check transaction.log size
        code, out, _ = controller.exec_cmd("[ -f /var/log/app/transaction.log ] && ls -s -k /var/log/app/transaction.log | awk '{print $1}' || echo 0")
        try:
            size_kb = int(out.strip().split()[-1])
        except Exception:
            size_kb = 0

        if size_kb > 10240:
            return False, f"/var/log/app/transaction.log is still consuming {size_kb // 1024}MB.", {"size_mb": size_kb // 1024}

        return True, "Both unlinked file descriptor and bloated log reclaimed successfully.", {"status": "healthy"}


class MetadataSaturationTimeoutScenario(Scenario):
    """Scenario: Inode exhaustion causing application timeout masked as network/service degradation."""

    id = "expert_004"
    category = "inodes"
    level = "EXPERT"
    difficulty = "EXPERT"
    title = "Critical Checkout Stall: Metadata Table Saturation Masked as Upstream Timeout"
    symptoms = [
        "Web application checkout sessions hang indefinitely and return HTTP 504 Gateway Timeout",
        "Application developers insist the external payment provider or database is timing out",
        "Server CPU, memory, and disk space (df -h) appear completely healthy",
    ]
    context = (
        "Incident Commander Briefing: The checkout service is experiencing high-latency stalls and 504 timeouts. "
        "The software engineering team suspects a downstream cloud service provider outage because "
        "the host has 90% free disk space, 4GB of free RAM, and low CPU load. "
        "However, external status dashboards report no provider incidents. "
        "Investigate host-level kernel resource constraints and eliminate the root cause of the session lockup."
    )
    objective = (
        "1. Look beyond high-level resource metrics (CPU, RAM, df -h) to inspect filesystem metadata.\n"
        "2. Identify 100% inode table exhaustion on /var/spool/app_cache using df -i.\n"
        "3. Purge the millions of orphaned session inodes and restore normal session creation."
    )
    expected_tools = ["df -i", "find", "rm", "strace"]
    investigation_guidance = (
        "When disk blocks are free but file creation fails, check metadata capacity. "
        "Run 'df -i' to inspect inode utilization across mount points. "
        "Notice that /var/spool/app_cache is at 100% inode usage. "
        "Purge the orphaned session files using 'find /var/spool/app_cache -type f -delete'."
    )
    hints = [
        "Standard 'df -h' displays block storage. Check metadata capacity tables using 'df -i'.",
        "Notice /var/spool/app_cache has 0 free inodes. The application cannot allocate an inode for new session tokens.",
        "Execute 'find /var/spool/app_cache -type f -delete' to clear the exhausted inode pool.",
    ]
    expected_root_cause = (
        "The '/var/spool/app_cache' filesystem suffered 100% inode exhaustion (IUse% = 100%), "
        "causing application session creation syscalls (open/creat) to fail with ENOSPC, "
        "which manifested as application hangs and 504 Gateway Timeouts."
    )
    expected_fix = (
        "Diagnosed metadata saturation via 'df -i', purged thousands of stale session files "
        "with 'find /var/spool/app_cache -type f -delete', and verified inode availability."
    )
    validation = "Confirm 'df -i /var/spool/app_cache' shows <20% inode usage and new files can be written."
    learning_points = [
        "How metadata saturation (inode exhaustion) masquerades as application timeouts and network delays",
        "Why monitoring systems must alert on both block capacity (df -h) and inode capacity (df -i)",
        "Designing cleanup cron jobs and ephemeral storage policies for high-frequency session directories",
    ]
    postmortem_sections = {
        "incident_summary": "E-Commerce checkout session timeout outage caused by filesystem inode metadata saturation.",
        "impact": "Customers experienced session creation lockups resulting in 504 Gateway Timeouts on checkout.",
        "detection": "Synthetics monitor detected 15-second response time spike on session endpoint.",
        "initial_hypotheses": "1. External payment gateway outage; 2. Database connection pool exhaustion; 3. Kernel metadata starvation.",
        "evidence_collected": "df -h showed 90% free blocks; df -i showed 100% inode usage on /var/spool/app_cache.",
        "root_cause": "Session tokens were written as individual 0-byte files without automated TTL expiration.",
        "contributing_factors": "Monitoring alerted only on disk byte consumption, not inode percentage.",
        "remediation": "Purged 2000 orphaned session files via find -delete; verified immediate latency recovery.",
        "validation": "Created test file successfully; verified live session creation returns HTTP 200.",
        "prevention": "Add Prometheus alert for node_filesystem_files_free and configure automated session pruning."
    }

    def setup(self, controller: LabController) -> bool:
        controller.exec_cmd(
            "mountpoint -q /var/spool/app_cache || "
            "sudo mount -t tmpfs -o size=10M,nr_inodes=2000 tmpfs /var/spool/app_cache"
        )
        controller.exec_cmd("sudo chmod 777 /var/spool/app_cache")
        setup_cmd = (
            "for i in $(seq 1 2000); do "
            "  touch /var/spool/app_cache/sess_$i 2>/dev/null || break; "
            "done"
        )
        controller.exec_cmd(setup_cmd, user="devops")
        code, _, err = controller.exec_cmd("touch /var/spool/app_cache/test_probe.tmp", user="devops")
        return code != 0 or "No space" in err

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        code, _, err = controller.exec_cmd(
            "touch /var/spool/app_cache/verify_probe.tmp && rm -f /var/spool/app_cache/verify_probe.tmp",
            user="devops"
        )
        if code != 0:
            return False, f"Cannot write to /var/spool/app_cache: {err}", {"creatable": False}

        _, out, _ = controller.exec_cmd("df -i /var/spool/app_cache | tail -n 1 | awk '{print $5}'")
        usage_pct = out.strip().replace("%", "")
        try:
            pct = int(usage_pct)
            if pct > 80:
                return False, f"Inode usage is still very high ({pct}%).", {"inode_pct": pct}
        except Exception:
            pass

        return True, "Inodes restored and checkout session creation verified.", {"status": "healthy"}


class StealthCryptominerScenario(Scenario):
    """Scenario: Disguised unauthorized process stealing compute cycles with masquerading."""

    id = "expert_005"
    category = "cpu"
    level = "EXPERT"
    difficulty = "EXPERT"
    title = "Security Incident Response: Stealth Resource Hijacking with Process Masquerading"
    symptoms = [
        "SOC Alert: Abnormal CPU compute consumption and sustained thread saturation",
        "Application response latency degraded across all production microservices",
        "Process list appears superficially normal to basic monitoring tools",
    ]
    context = (
        "Security Operations Center (SOC) Alert: Automated anomaly detection flagged suspicious "
        "compute activity on prod-app-server-01. Host CPU load is near 100%, causing severe response degradation. "
        "Standard dashboard charts show high compute, but the process appears named '[systemd-journald]'. "
        "Conduct a security triage: inspect process ownership, verify executable binary paths, "
        "terminate the unauthorized workload, and restore host operational stability."
    )
    objective = (
        "1. Identify the masquerading compute-hijacking process using /proc/<PID>/exe and ps.\n"
        "2. Safely terminate the rogue workload using SIGKILL.\n"
        "3. Verify that CPU utilization returns to baseline and critical services are healthy."
    )
    expected_tools = ["ps", "top", "ls -l /proc/*/exe", "kill", "uptime"]
    investigation_guidance = (
        "Notice the high-CPU process disguised as '[systemd-journald]'. "
        "Inspect the process with 'ps -eo pid,user,ppid,args --sort=-%cpu | head -n 10'. "
        "Check its actual binary on disk using 'ls -l /proc/<PID>/exe'. "
        "Observe that it points to python3 (not systemd-journald) and runs under user 'devops'. "
        "Terminate the rogue process with 'kill -9 <PID>'."
    )
    hints = [
        "A process name in ps can be spoofed by modifying argv[0]. Check the real executable target via /proc/<PID>/exe.",
        "Look for high CPU tasks owned by non-root users claiming to be system daemons like '[systemd-journald]'.",
        "Terminate the imposter process with 'pkill -9 -f cryptonight' (or kill -9 <PID>).",
    ]
    expected_root_cause = (
        "An unauthorized rogue compute task ('cryptonight') executed with spoofed process name '[systemd-journald]' "
        "under user 'devops', saturating a CPU core at 100% and degrading production service latency."
    )
    expected_fix = (
        "Audited process executable links via '/proc/<PID>/exe', uncovered the masquerading binary, "
        "and terminated the unauthorized process via 'kill -9 <PID>'."
    )
    validation = "Confirm CPU load returns to baseline (<10%) and 'pgrep -f cryptonight' returns empty."
    learning_points = [
        "Understanding Linux process spoofing via prctl(PR_SET_NAME) and exec -a",
        "Using /proc/<PID>/exe (symlink to actual ELF binary) to defeat process name masquerading",
        "Integrating security threat triage with SRE performance troubleshooting",
    ]
    postmortem_sections = {
        "incident_summary": "Security incident: unauthorized compute-hijacking process executed under masqueraded daemon name.",
        "impact": "CPU saturation degraded API response times by 400% for all co-located microservices.",
        "detection": "Host CPU anomaly alert fired when load average exceeded core count threshold.",
        "initial_hypotheses": "1. Legitimate systemd-journald logging loop; 2. Application thread lockup; 3. Masquerading compute process.",
        "evidence_collected": "/proc/<PID>/exe pointed to /usr/bin/python3, not systemd-journald. UID was 1000 (devops), not 0.",
        "root_cause": "Unauthorized script executed with exec -a '[systemd-journald]' to bypass casual process auditing.",
        "contributing_factors": "Lack of runtime binary integrity monitoring on execution namespace.",
        "remediation": "Terminated rogue PID via SIGKILL; validated CPU recovery.",
        "validation": "Confirmed process table clean and core services responding within SLA.",
        "prevention": "Deploy eBPF-based security monitoring (e.g., Falco/Tetragon) to detect process masquerading in real time."
    }

    def setup(self, controller: LabController) -> bool:
        cmd = (
            "nohup bash -c 'exec -a \"[systemd-journald]\" python3 -c \""
            "import time\n"
            "# cryptonight marker\n"
            "x = 0\n"
            "while True:\n"
            "    x = (x + 1) % 10000000\n"
            "\"' > /dev/null 2>&1 &"
        )
        controller.exec_cmd(cmd, user="devops")
        time.sleep(1)
        code, out, _ = controller.exec_cmd("pgrep -f cryptonight")
        if code != 0 or not out.strip():
            # Check for systemd-journald python task
            code, out, _ = controller.exec_cmd("pgrep -f systemd-journald")
        return code == 0 and len(out.strip()) > 0

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check if the process is dead
        code1, out1, _ = controller.exec_cmd("pgrep -f cryptonight")
        code2, out2, _ = controller.exec_cmd("pgrep -f systemd-journald")
        if (code1 == 0 and out1.strip()) or (code2 == 0 and out2.strip()):
            return False, "Masquerading process is still running.", {"pids": (out1 + " " + out2).strip()}

        h_code, h_out, _ = controller.exec_cmd("curl -s http://localhost:8080/health")
        if h_code != 0 or "UP" not in h_out:
            return False, "Masquerading process stopped but web-app is not responding.", {"health": "fail"}

        return True, "Security incident resolved: unauthorized compute process terminated and services healthy.", {"status": "healthy"}
