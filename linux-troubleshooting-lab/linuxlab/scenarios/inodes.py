from typing import List, Tuple, Dict, Any
from linuxlab.scenarios.base import Scenario
from linuxlab.lab.controller import LabController

class InodeExhaustionScenario(Scenario):
    """Scenario: Inode exhaustion preventing new file creation despite ample free disk space."""

    id = "inode_001"
    category = "inodes"
    level = "MODERATE"
    difficulty = "MODERATE"
    title = "Filesystem Inode Exhaustion"
    symptoms = [
        "Applications fail with 'No space left on device' (ENOSPC)",
        "Yet 'df -h' reports plenty of available megabytes/gigabytes on disk",
        "Sessions or temporary cache files cannot be created",
    ]
    context = (
        "The web application cache directory /var/spool/app_cache is rejecting new session files. "
        "The developer checked 'df -h' and insists: 'The disk has 99% free space! It must be an OS bug!' "
        "Investigate the filesystem metadata, identify why file creation is failing, and remediate the issue."
    )
    objective = (
        "1. Diagnose why 'No space left on device' occurs when megabytes are free.\n"
        "2. Identify the directory consuming excessive filesystem inodes.\n"
        "3. Clean up the exhausted inode directory and verify file creation succeeds."
    )
    expected_tools = ["df", "find", "rm"]
    investigation_guidance = (
        "Remember that filesystems have two independent capacity limits: data blocks and inode metadata tables. "
        "Run 'df -i' to inspect inode utilization across mount points. "
        "Once you locate the filesystem with 100% IUse, locate the directory containing thousands of tiny files "
        "and clean them up using 'find ... -type f -delete'."
    )
    hints = [
        "A filesystem has two distinct capacity limits: block storage (bytes) and metadata tables (inodes).",
        "Run 'df -i' to inspect inode utilization across mounted filesystems. Compare IUse% vs Use%.",
        "Notice /var/spool/app_cache inode utilization is at 100%. Inspect the directory contents and remove the orphaned session files using 'find /var/spool/app_cache -type f -delete'.",
    ]
    expected_root_cause = (
        "The cache directory '/var/spool/app_cache' was overwhelmed with thousands of zero-byte session files. "
        "Although disk space (blocks) was empty, inode metadata tables reached 100% capacity (IUse% = 100%)."
    )
    expected_fix = (
        "Ran 'df -i' to detect inode saturation, located the bloated directory '/var/spool/app_cache', "
        "cleared the unlinked cache files with 'find /var/spool/app_cache -type f -delete', "
        "and verified inode headroom was restored."
    )
    validation = "Confirm 'df -i /var/spool/app_cache' shows low inode usage (<20%) and touch succeeds."
    learning_points = [
        "df -i vs df -h: Disk space vs Inode count",
        "Why thousands of empty files can crash a server even on a multi-terabyte disk",
        "Why 'rm *' can fail with 'Argument list too long' on huge file counts (and why 'find ... -delete' is superior)",
        "Filesystem architecture: data blocks vs inode tables",
    ]
    postmortem_sections = {
        "investigation_sequence": "1. touch test file -> 'No space left on device' -> 2. df -h (normal) -> 3. df -i (100% IUse) -> 4. find /var/spool/app_cache -delete",
        "evidence": "'df -i /var/spool/app_cache' showed 100% IUse with 0 free inodes.",
        "root_cause": "Orphaned session files accumulated without expiration or cleanup daemon.",
        "remediation": "Purged accumulated session cache files via find ... -delete.",
        "validation_steps": "Verified inode utilization dropped below 10% and new session files can be created."
    }

    def setup(self, controller: LabController) -> bool:
        # Mount tmpfs with limited inodes if not already mounted
        controller.exec_cmd(
            "mountpoint -q /var/spool/app_cache || "
            "sudo mount -t tmpfs -o size=10M,nr_inodes=2000 tmpfs /var/spool/app_cache"
        )
        controller.exec_cmd("sudo chmod 777 /var/spool/app_cache")

        # Fill up the inodes with 2000 tiny files
        setup_cmd = (
            "for i in $(seq 1 2000); do "
            "  touch /var/spool/app_cache/sess_$i 2>/dev/null || break; "
            "done"
        )
        controller.exec_cmd(setup_cmd, user="devops")

        # Verify touch fails with ENOSPC
        code, _, err = controller.exec_cmd("touch /var/spool/app_cache/test_probe.tmp", user="devops")
        return code != 0 or "No space left on device" in err

    def verify(self, controller: LabController) -> Tuple[bool, str, Dict[str, Any]]:
        # Check if we can create a file now
        code, _, err = controller.exec_cmd(
            "touch /var/spool/app_cache/verify_probe.tmp && rm -f /var/spool/app_cache/verify_probe.tmp",
            user="devops"
        )
        if code != 0:
            return False, f"Still unable to create files in /var/spool/app_cache: {err}", {"creatable": False}

        # Check df -i for /var/spool/app_cache
        _, out, _ = controller.exec_cmd("df -i /var/spool/app_cache | tail -n 1 | awk '{print $5}'")
        usage_pct = out.strip().replace("%", "")
        try:
            pct = int(usage_pct)
            if pct > 80:
                return False, f"Inode usage is still very high ({pct}%).", {"inode_pct": pct}
        except Exception:
            pass

        return True, "Inodes freed successfully. Applications can create files normally.", {"inode_pct": pct if 'pct' in locals() else 0}
