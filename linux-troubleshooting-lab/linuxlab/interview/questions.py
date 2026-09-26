from typing import List, Dict, Any, Optional

INTERVIEW_SCENARIOS: List[Dict[str, Any]] = [
    # EASY: Basic Linux reasoning
    {
        "id": "q_easy_top_kill",
        "level": "EASY",
        "topic": "Process Monitoring & Signals",
        "initial_prompt": (
            "Scenario:\n"
            "An application server is suddenly sluggish. You SSH in and want to determine\n"
            "which process is consuming the most CPU, and terminate it safely.\n\n"
            "Which commands would you use to find the process and stop it?"
        ),
        "follow_ups": [
            "What is the difference between SIGTERM (kill -15) and SIGKILL (kill -9)?",
            "Why is it recommended to send SIGTERM before SIGKILL in production?",
            "Which command displays processes sorted by memory usage?",
        ],
        "sre_breakdown": (
            "DevOps Fundamentals Benchmark:\n"
            "1. Discovery: 'top' (press P for CPU, M for RAM) or 'ps aux --sort=-%cpu | head -n 10'.\n"
            "2. Signal Handling: SIGTERM (15) politely notifies the application process to flush buffers, "
            "close file descriptors, and cleanly disconnect sessions. SIGKILL (9) is handled by the kernel "
            "directly, immediately destroying the task without cleanup.\n"
            "3. Best Practice: Always attempt 'kill -15 <PID>' first; wait 5-10 seconds; escalate to 'kill -9 <PID>' "
            "only if the process is completely hung."
        )
    },
    # MODERATE: Multi-command investigation
    {
        "id": "q_mod_service_restart",
        "level": "MODERATE",
        "topic": "Service Lifecycle & Journal Logs",
        "initial_prompt": (
            "Scenario:\n"
            "After an automated package update, 'systemctl status nginx' reports 'failed (Result: exit-code)'.\n"
            "Attempts to restart it with 'systemctl restart nginx' fail with exit status 1.\n\n"
            "Walk through your step-by-step investigation to discover the root cause and bring the service online."
        ),
        "follow_ups": [
            "Which command lets you view the detailed stderr logs from systemd units?",
            "How would you validate the configuration file syntax before attempting another restart?",
            "What command would you run if a rogue process is already listening on port 80?",
        ],
        "sre_breakdown": (
            "Junior DevOps Benchmark:\n"
            "1. Log Analysis: Run 'journalctl -xeu nginx.service --no-pager' to view the exact error trace.\n"
            "2. Config Pre-flight Validation: Run configuration test commands prior to restarting daemons (e.g. 'nginx -t', 'sshd -t', or 'python3 -m json.tool <config>').\n"
            "3. Port Collision: Inspect sockets with 'ss -tulpn | grep :80' or 'lsof -i :80' to check if an abandoned daemon holds the binding socket."
        )
    },
    # FLUENT: Junior DevOps incident reasoning
    {
        "id": "q_load_iowait",
        "level": "FLUENT",
        "topic": "CPU & Load Average",
        "initial_prompt": (
            "Scenario:\n"
            "Your production Linux server has a 1-minute load average of 18.0 on an 8-core CPU.\n"
            "However, when you run 'top', overall CPU utilization is only 25% (%usr + %sys).\n\n"
            "What could explain this high load average with low CPU utilization?"
        ),
        "follow_ups": [
            "What does Linux load average actually measure compared to CPU utilization?",
            "Which command and metric would you check next to confirm this hypothesis?",
            "If processes are in 'D' state (uninterruptible sleep), can you terminate them with 'kill -9'?",
        ],
        "sre_breakdown": (
            "Senior SRE Assessment:\n"
            "1. Root Explanation: On Linux, Load Average counts processes in R (Running) state AND D (Uninterruptible Sleep) state.\n"
            "   High load with low CPU utilization almost always indicates I/O wait saturation (processes waiting on slow disk, NFS, or block device).\n"
            "2. Investigation Tools: Check 'vmstat 1' (look at 'b' column for blocked processes and 'wa' column for iowait).\n"
            "   Use 'iostat -xz 1' to check %util and await per disk partition.\n"
            "   Use 'ps aux | awk \"$8 ~ /D/\"' to find processes in uninterruptible sleep.\n"
            "3. Key Production Fact: Processes in 'D' state are waiting on kernel/driver I/O syscalls and CANNOT be killed even with SIGKILL (kill -9)."
        )
    },
    # ADVANCED: SRE-style diagnosis & storage internals
    {
        "id": "q_open_deleted_files",
        "level": "ADVANCED",
        "topic": "Storage & File Descriptors",
        "initial_prompt": (
            "Scenario:\n"
            "An on-call alert fired: '/var/log' filesystem is 100% full.\n"
            "A junior engineer deleted a 50GB active log file using 'rm /var/log/app/huge.log'.\n"
            "However, 'df -h' still reports 100% full, but 'du -sh /var/log' shows only 2GB used.\n\n"
            "Why is 'df' still showing 100% full, and how do you resolve it?"
        ),
        "follow_ups": [
            "What is the difference in how 'df' vs 'du' calculate disk usage?",
            "Which command reveals the process holding the deleted file descriptor open?",
            "How do you safely free the space without restarting the whole server or dropping connections?",
        ],
        "sre_breakdown": (
            "Senior SRE Assessment:\n"
            "1. Root Explanation: 'rm' unlinks the directory entry (dentry), but the inode and data blocks are NOT freed "
            "   until all open file descriptors referencing that inode are closed by running processes.\n"
            "   'df' queries filesystem superblocks (accounting for all allocated blocks), while 'du' traverses directory trees (which no longer see the unlinked file).\n"
            "2. Investigation Tool: 'lsof +L1' or 'lsof | grep deleted' immediately reveals the PID holding the deleted file descriptor.\n"
            "3. Production Remediation: Safely truncate the file descriptor via procfs without killing the service: "
            "   '> /proc/<PID>/fd/<FD_NUM>', or reload the daemon gracefully ('kill -HUP <PID>')."
        )
    },
    # ADVANCED: Networking & Name Resolution
    {
        "id": "q_dns_nsswitch",
        "level": "ADVANCED",
        "topic": "Networking & Name Resolution",
        "initial_prompt": (
            "Scenario:\n"
            "On your production host, 'curl https://internal-api.service.corp' fails with 'Could not resolve host'.\n"
            "However, when you run 'dig internal-api.service.corp' or 'nslookup internal-api.service.corp', it returns the correct IP immediately.\n\n"
            "How can 'dig' succeed while 'curl' (and your application) fails?"
        ),
        "follow_ups": [
            "How does 'dig' perform DNS resolution compared to standard libc/curl?",
            "Which configuration files control how standard applications resolve hostnames in Linux?",
            "What would you inspect in /etc/nsswitch.conf and /etc/hosts?",
        ],
        "sre_breakdown": (
            "Senior SRE Assessment:\n"
            "1. Root Explanation: 'dig' and 'nslookup' bypass the OS NSS (Name Service Switch) resolver entirely "
            "   and speak directly to the nameserver specified in /etc/resolv.conf.\n"
            "   Applications and 'curl' use libc 'getaddrinfo()', which consults '/etc/nsswitch.conf' (hosts: files dns).\n"
            "2. Common Causes: A stale or typo entry in '/etc/hosts' overriding DNS, missing 'dns' in '/etc/nsswitch.conf', "
            "   or bad 'search' domains / ndots in '/etc/resolv.conf'.\n"
            "3. Diagnostic Command: 'getent hosts internal-api.service.corp' tests the exact libc resolution path."
        )
    },
    # EXPERT: Production incident interview
    {
        "id": "q_expert_socket_backlog",
        "level": "EXPERT",
        "topic": "TCP Socket Backlog & SYN Drops",
        "initial_prompt": (
            "Scenario:\n"
            "During a peak traffic event, external API gateways report random 502/504 timeouts connecting to your backend.\n"
            "The backend host has 50% CPU idle, 16GB free RAM, network bandwidth is under 20% utilization,\n"
            "and application error logs are completely empty. Connection failures occur before requests hit application code.\n\n"
            "What kernel/TCP layer bottlenecks would you investigate to explain silent connection drops under high load?"
        ),
        "follow_ups": [
            "What are the SYN backlog (tcp_max_syn_backlog) and Listen backlog (somaxconn)?",
            "Which command and metric counters reveal dropped SYN packets or listen queue overflows?",
            "How does TCP SYN cookies (tcp_syncookies) interact with socket queues under burst traffic?",
        ],
        "sre_breakdown": (
            "Staff SRE Architecture Benchmark:\n"
            "1. Kernel Bottlenecks: When connection rate surges, the TCP listen backlog queue fills up. If the application's accept() loop cannot keep pace with incoming connections, the kernel drops new SYN packets or ignores SYNs, resulting in connection timeouts at the client.\n"
            "2. Diagnostic Metrics: Run 'netstat -s | grep -i listen' (look for 'times the listen queue of a socket overflowed' and 'SYNs to LISTEN sockets dropped'). Run 'ss -lnt' and check the 'Send-Q' (backlog limit) vs 'Recv-Q' (current backlog depth).\n"
            "3. Kernel Tuning: Increase 'net.core.somaxconn' and 'net.ipv4.tcp_max_syn_backlog' in sysctl.conf, ensure application listen() backlog parameter matches, and inspect worker concurrency."
        )
    }
]

def get_interview_scenarios_for_level(level: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filter interview scenarios by level, falling back to all."""
    if not level:
        return INTERVIEW_SCENARIOS
    filtered = [q for q in INTERVIEW_SCENARIOS if q.get("level", "").upper() == level.upper()]
    return filtered if filtered else INTERVIEW_SCENARIOS
