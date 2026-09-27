from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class DiskSpaceScenario(Scenario):
    """Scenario: Large unrotated log file consuming disk space."""

    id = "disk_001"
    category = "disk"
    level = "EASY"
    difficulty = "EASY"
    title = "Unrotated Application Log Consuming Disk Space"
    symptoms = [
        "Applications failing to flush temporary buffers or transaction states",
        "Syslog alerts indicating filesystem space threshold exceeded",
        "Disk space alarms firing on prod-app-server-01",
    ]
    context = (
        "The application team reported that transaction logging has stalled. "
        "Attempts to write temporary files or logs result in disk write errors. "
        "A rogue debug trace was left enabled in the payment logging system overnight. "
        "Investigate the filesystem, identify what consumed the disk space, and safely recover capacity."
    )
    objective = (
        "1. Identify the filesystem and directory consuming abnormal disk space.\n"
        "2. Locate the oversized file(s).\n"
        "3. Safely reclaim space (truncate or remove the bloated log) and verify free space."
    )
    expected_tools = ["df", "du", "find", "head", "tail"]
    investigation_guidance = (
        "First check filesystem capacity with 'df -h'. Next, search inside directories with 'du -sh /var/log/app/*' "
        "or find files larger than 100MB using 'find /var/log -type f -size +100M'. "
        "Safely truncate the oversized log file using '> /path/to/file.log'."
    )
    hints = [
        "First determine what resource is actually exhausted.",
        "Identify the affected filesystem, then narrow the investigation to the directories consuming the most space.",
        "Look for unusually large files in the application logging area and confirm the culprit before modifying anything. Safely truncate the oversized log file using '> /var/log/app/transaction.log'.",
    ]
    expected_root_cause = (
        "A runaway debug trace accumulated in '/var/log/app/transaction.log', "
        "consuming hundreds of megabytes and causing filesystem write degradation."
    )
    expected_fix = (
        "Used 'df -h' and 'du -sh /var/log/app/*' to pinpoint '/var/log/app/transaction.log', "
        "then truncated the file using '> /var/log/app/transaction.log' (or removed it) "
        "and confirmed disk capacity was reclaimed."
    )
    validation = "Check 'df -h' to confirm free disk space is restored and verify you can create files in '/var/log/app'."
    learning_points = [
        "df -h vs du -sh (filesystem allocation vs directory tree usage)",
        "Why truncating (> file.log) is safer than 'rm' on an actively open file handle (lsof | grep deleted)",
        "find /path -type f -size +100M for rapid file discovery",
        "Configuring logrotate to prevent unconstrained log growth in production",
    ]
    postmortem_sections = {
        "what_happened": "An unrotated transaction log grew to 350MB due to debug logging, filling the disk partition.",
        "commands_used": "df -h; du -sh /var/log/app/*; > /var/log/app/transaction.log; df -h",
        "output_meaning": "'df -h' showed high block usage; 'du -sh' located the single massive log file.",
        "why_fix_worked": "Truncating the file zeroed its size immediately, releasing blocks back to the filesystem."
    }

    def setup(self, controller: LabController) -> bool:
        # Create a large 350MB bloated log file
        setup_cmd = (
            "fallocate -l 350M /var/log/app/transaction.log 2>/dev/null || "
            "dd if=/dev/zero of=/var/log/app/transaction.log bs=1M count=350 2>/dev/null"
        )
        code, _, _ = controller.exec_cmd(setup_cmd, user="devops")
        if code != 0:
            return False

        # Verify file size > 200MB
        v_code, out, _ = controller.exec_cmd("ls -s -k /var/log/app/transaction.log | awk '{print $1}'")
        try:
            size_kb = int(out.strip())
            return size_kb > 200000
        except Exception:
            return False

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check if the bloated file still exists and exceeds 10MB
        code, out, _ = controller.exec_cmd(
            "[ -f /var/log/app/transaction.log ] && ls -s -k /var/log/app/transaction.log | awk '{print $1}' || echo 0"
        )
        try:
            size_kb = int(out.strip().split()[-1])
        except Exception:
            size_kb = 0

        if size_kb > 10240:  # > 10MB
            return False, f"/var/log/app/transaction.log is still consuming {size_kb // 1024}MB.", {"size_mb": size_kb // 1024}

        # Verify we can write to /var/log/app
        w_code, _, _ = controller.exec_cmd("touch /var/log/app/verify.tmp && rm -f /var/log/app/verify.tmp")
        if w_code != 0:
            return False, "Space was not properly reclaimed; unable to write test file to /var/log/app.", {}

        return True, "Disk space successfully reclaimed. Logging directory is healthy.", {"freed": True}
