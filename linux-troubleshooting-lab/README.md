# Linux Troubleshooting Lab — Progressive DevOps & SRE Practice Environment

A safe, disposable, production-grade Linux troubleshooting practice laboratory for DevOps and Site Reliability Engineers.

Rather than static multiple-choice quizzes, `linuxlab` simulates realistic production incidents inside an isolated Docker container (`linuxlab-sandbox`). Learners investigate real symptoms, inspect processes, logs, sockets, and filesystems using authentic Linux utilities, formulate hypotheses, apply fixes, and receive automated post-mortem evaluations.

---

## Architecture Overview

```
User (Browser or CLI)
  │
  ├── Browser UI: http://localhost:8088 (xterm.js + WebSockets + Dashboard)
  └── CLI: bin/linuxlab or python3 -m linuxlab.cli
        ├── Progressive Scenario Engine & Registry (25 Scenarios / 5 Levels)
        ├── Lab Controller (linuxlab/lab/controller.py)
        ├── Deterministic Evaluator & Scorer (linuxlab/evaluation/)
        ├── State & Level Mastery Tracker (linuxlab/state/manager.py)
        └── Optional Local AI Engine (linuxlab/ai/ollama.py -> Ollama)
        │
        ▼ (docker exec / pty / docker compose)
Disposable Sandbox Container (`linuxlab-sandbox`)
  ├── Hostname: prod-app-server-01
  ├── Users: devops (sudo), appuser, root
  ├── Production Services:
  │     ├── web-app.service (HTTP 8080: /health, /metrics)
  │     └── payment-api.service (HTTP 8000: /health, /process-payment)
  └── Tools: procps, iproute2, sysstat, htop, lsof, strace, curl, jq, vim, nano, etc.
```

---

## Safety & Isolation Model

* **100% Host Isolation**: All fault injections (CPU burns, memory hogs, unlinked file leaks, socket conflicts, permission drifts, zombie floods) execute strictly inside the Docker container `linuxlab-sandbox`.
* **Zero Host Impact**: No host processes, filesystems, network configurations, or WSL distributions are modified.
* **Deterministic Reset**: `linuxlab reset` (or the **Reset Lab** button in the UI) restores the container to a clean, healthy production baseline in seconds via `/opt/scripts/clean_state.sh`.

---

## Progressive Learning Levels

The lab features 5 difficulty levels that govern scenario complexity, symptom ambiguity, investigation guidance, hint behavior, and post-mortem depth:

| Level | Target Audience | Investigation Guidance | Hint Behavior | Post-Mortem Format | Scoring Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EASY** | Beginners / Linux fundamentals | Explicit guidance & suggested tools displayed | 1. Area to Inspect<br>2. Suggested Command<br>3. Targeted Resolution | **Beginner Post-Mortem** (What Happened, Commands Used, Output Meaning, Why Fix Worked) | Base 100, standard hint deductions |
| **MODERATE** | Junior transition (multi-command correlation) | Subsystem hints without direct answers | 1. Investigation Direction<br>2. Subsystem & Tool<br>3. Correlated Clue | **Junior Transition Post-Mortem** (Sequence, Evidence, Root Cause, Remediation, Validation) | Time and hint deductions |
| **FLUENT** | Realistic DevOps production incidents | Minimal guidance, self-directed commands | 1. Conceptual Direction<br>2. Hypothesis Clue<br>3. Evidence Clue | **DevOps Post-Mortem** (Methodology, Evidence, Ruled Out Causes, Remediation) | Time and hint deductions |
| **ADVANCED** | Senior cross-layer & multi-signal incidents | Multi-signal alerts, competing failure modes | 1. Broad Subsystem Direction<br>2. Signal Correlation Clue<br>3. Root Cause Clue | **Advanced SRE Post-Mortem** (Cross-Layer Correlation, Eliminated Hypotheses, Blast Radius) | **Command Efficiency Penalty** (>40 commands = -5 pts), Reasoning Bonus (+5 to +10 pts) |
| **EXPERT** | Ambiguous P0/P1 production outages | High ambiguity, stealth faults, phantom timeouts | 1. Investigation Reasoning<br>2. Diagnostic Principle<br>3. Hypothesis Elimination | **10-Point Production SRE Post-Mortem** (Summary, Impact, Detection, Hypotheses, Evidence, Root Cause, Contributing Factors, Remediation, Validation, Prevention) | **Command Efficiency Penalty** (>40 commands = -5 pts), Reasoning Bonus (+5 to +10 pts) |

---

## Scenario Catalog (25 Production Scenarios)

### Level 1: EASY (Foundational Commands & Clear Failures)
1. `cpu_001`: Runaway Background Worker Pegging CPU (`ps`, `top`, `kill`)
2. `mem_001`: Memory Leak Approaching Out-Of-Memory (`free`, `vmstat`, `pkill`)
3. `disk_001`: Rapid Disk Space Exhaustion From Unrotated Debug Log (`df`, `du`, `rm`)
4. `perm_001`: Web Application Permission Denied on Local Cache (`ls -la`, `chmod`)
5. `easy_005`: Essential Web Application Service Inactive (`systemctl status`, `systemctl start`)

### Level 2: MODERATE (Multi-Command Correlation)
6. `inode_001`: Disk Full Error While Storage Space Shows 90% Free (`df -i`, `find`)
7. `service_001`: Web App CrashLoop Due to Missing Runtime Cache Directory (`systemctl`, `journalctl`, `mkdir`)
8. `net_001`: Web Application Port Conflict (`ss -tulpn`, `lsof`, `kill`)
9. `log_001`: Application Log Diagnosis of Downstream Database Failure (`tail`, `/etc/hosts`, `curl`)
10. `mod_005`: Application Log File Permission Mismatch Preventing Service Boot (`chown`, `systemctl`)

### Level 3: FLUENT (Realistic Production Incidents)
11. `fluent_001`: Service Startup Aborted by Stale Process Lock (`/run/services/*.pid`, `ss`)
12. `fluent_002`: Storage Capacity Alert Persists After File Deletion (`lsof +L1`, `kill`)
13. `fluent_003`: Port Configuration Drift Breaking Reverse Proxy Routing (`netstat`, `config.conf`)
14. `fluent_004`: CPU Starvation Caused by Disguised Worker Process (`ps aux`, `htop`, `kill`)
15. `fluent_005`: Downstream Database Port Mismatch Under Heavy Traffic (`/etc/app/payment.conf`, `curl`)

### Level 4: ADVANCED (Multi-Signal & Cross-Layer Failures)
16. `adv_001`: Cascading Dual-Layer Resolution Failure Across Microservices (`/etc/hosts` + `/etc/app/payment.conf`)
17. `adv_002`: Silent Read-Only Mount Degrading Cache Subsystem (`mount -o remount,rw`)
18. `adv_003`: Configuration File Permission Drift Compounded by Zombie Port Binding (`chmod` + `pkill`)
19. `adv_004`: Unreaped Zombie Flood Saturating Process Table (`ps -el`, `ppid`, `kill -9 <parent>`)
20. `adv_005`: Stealth Memory Leak With High Kernel Buffer Allocation (`free -m`, `vmstat`, `pkill`)

### Level 5: EXPERT (Ambiguous Production Outages & SRE Reasoning)
21. `expert_001`: P1 Outage: Intermittent Downstream Timeout with Phantom Gateway Failures
22. `expert_002`: Catastrophic Rollout Abort: Multi-Service Deadlock and Corrupted State
23. `expert_003`: Silent Disk Full: Shadowed File Descriptors and Unlinked Storage Ingestion
24. `expert_004`: Production Application Freezing Due to Ephemeral Inode Exhaustion
25. `expert_005`: Stealth Rogue Miner Disguised as Core Systemd Worker

---

## Prerequisites

* **OS**: Linux or WSL2 (Ubuntu 20.04/22.04+)
* **Docker & Docker Compose**: Docker Engine v20.10+ and Docker Compose v2+
* **Python**: Python 3.10+

---

## Quick Start Guide

### 1. Start the Lab Environment
```bash
# Clone the repository (if not already cloned)
git clone <repo>
cd DevOps-Labs/linux-troubleshooting-lab

# Build and start both the sandbox container and the web UI
docker compose up -d --build

# Verify services are running
docker compose ps
```

### 2. Access the Web UI
Open **`http://localhost:8088`** in your browser. Both the web UI dashboard and interactive `linuxlab-sandbox` terminal are immediately ready.

### 3. Practice Flow
1. Select a difficulty level on the top bar (`EASY`, `MODERATE`, `FLUENT`, `ADVANCED`, or `EXPERT`).
2. Click **Random Incident** (or select a scenario from the **Scenario Library**).
3. Investigate in the browser terminal connected directly to `linuxlab-sandbox`.
4. Run commands to diagnose root cause and apply remediation.
5. Click **Evaluate**, describe your findings, and view your score and structured post-mortem.
6. Check the **Progress** tab to track your Level Mastery (`████████░░`) and success rates.

---

## Running the Automated Test Suites

The lab includes comprehensive unit test suites:

```bash
# 1. Run the original 8 scenarios end-to-end injection & verify tests
python3 -m unittest tests/test_scenarios.py

# 2. Run the progressive level architecture, scoring, and registry tests
python3 -m unittest tests/test_progressive_levels.py
```

---

## CLI Reference

You can also operate the lab directly from the terminal CLI:

```bash
# Start container
./bin/linuxlab start

# Inject an incident by level
./bin/linuxlab random --level EASY
./bin/linuxlab random --level EXPERT

# Check status
./bin/linuxlab status

# Open interactive shell in sandbox
./bin/linuxlab shell

# Request progressive hint
./bin/linuxlab hint

# Evaluate solution
./bin/linuxlab evaluate -e "Terminated rogue process on port 8080 and restarted service"

# View level mastery progress
./bin/linuxlab progress

# Reset lab to clean baseline
./bin/linuxlab reset
```
