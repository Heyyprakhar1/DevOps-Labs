# Linux Troubleshooting Lab — Progressive DevOps & SRE Practice Platform

A safe, disposable, production-grade Linux troubleshooting practice platform for DevOps and Site Reliability Engineers, featuring multi-user authentication, isolated sandbox containers, 4-dimensional state-based evaluation, and persistent learning metrics.

Rather than static multiple-choice quizzes, `linuxlab` simulates realistic production incidents inside isolated Docker sandbox containers. Learners investigate real symptoms, inspect processes, logs, sockets, and filesystems using authentic Linux utilities, formulate hypotheses, apply fixes, and receive automated post-mortem evaluations.

---

## Architecture Overview

```
                        ┌─────────────────────────────────────────────────────────┐
                        │             Learners & SRE Practitioners                │
                        └───────────────┬─────────────────────────┬───────────────┘
                                        │                         │
                               (HTTP/REST & WebSockets)          (CLI)
                                        │                         │
                                        ▼                         │
┌───────────────────────────────────────────────────────────────┐ │
│                 LinuxLab Platform (Port 8088)                 │ │
│                                                               │ │
│  ┌────────────────────────┐    ┌───────────────────────────┐  │ │
│  │   Authentication &     │    │  Session & Isolation      │  │ │
│  │   Token Verification   │    │  Manager (SandboxManager) │  │ │
│  └───────────┬────────────┘    └─────────────┬─────────────┘  │ │
│              │                               │                │ │
│  ┌───────────▼────────────┐    ┌─────────────▼─────────────┐  │ │
│  │ Persistent SQLite DB   │    │ Terminal WebSocket Proxy  │  │ │
│  │ (~/.linuxlab/          │    │ (pty fork to isolated     │  │ │
│  │  linuxlab.db)          │    │  user container)          │  │ │
│  └────────────────────────┘    └─────────────┬─────────────┘  │ │
│                                              │                │ │
│  ┌───────────────────────────────────────────▼─────────────┐  │ │
│  │ 4-Dimensional State-Based Incident Evaluator            │  │ │
│  │ (System State + Root Cause + Remediation + Explanation) │  │ │
│  └─────────────────────────────────────────────────────────┘  │ │
└───────────────────────────────┬───────────────────────────────┘ │
                                │ (Docker API / Unix Socket)      │
                                ▼                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Isolated Sandbox Fleet                          │
│                                                                        │
│   ┌──────────────────────────────┐    ┌──────────────────────────────┐ │
│   │ Sandbox A (User A)           │    │ Sandbox B (User B)           │ │
│   │ linuxlab-sandbox-usrA-sessA  │    │ linuxlab-sandbox-usrB-sessB  │ │
│   │  ├── Hostname: prod-app-01   │    │  ├── Hostname: prod-app-01   │ │
│   │  ├── Limits: 512MB, 1.0 CPU  │    │  ├── Limits: 512MB, 1.0 CPU  │ │
│   │  └── Fault: Injected disk_001│    │  └── Fault: Injected cpu_001 │ │
│   └──────────────────────────────┘    └──────────────────────────────┘ │
│                                                                        │
│   ┌──────────────────────────────┐                                     │
│   │ Standby/CLI Sandbox          │                                     │
│   │ linuxlab-sandbox (default)   │                                     │
│   └──────────────────────────────┘                                     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Core Capabilities & Features

### 1. Multi-User Authentication & Authorization
* **Secure Registration & Login**: Authenticate with unique usernames and strong passwords hashed with industry-standard `bcrypt`.
* **Session Tokens & Cookies**: Bearer token authorization in API headers and secure cookies for frontend convenience.
* **Server-Side Authorization**: Strict tenant boundaries. User A cannot access User B's active incident, view User B's history, evaluate User B's container, or connect to User B's terminal WebSocket.

### 2. Isolated User Sandboxes & Dynamic Lifecycle
* **No Shared Sandboxes**: Every active incident runs in its own dedicated Docker container named deterministically: `linuxlab-sandbox-<user_id[:8]>-<session_id[:8]>`.
* **Strict Resource Limits**: Sandboxes enforce `--memory=512m`, `--cpus=1.0`, and `--pids-limit=256` to prevent resource hogging or denial of service on host machines.
* **Automatic Cleanup**: Containers are automatically destroyed when an incident is solved or explicitly abandoned (`/api/incidents/reset`). Stale or orphaned containers older than 2 hours are pruned on platform restart.

### 3. Authorized Terminal WebSocket Connection
* Browser terminal connects via WebSocket to `/ws/terminal?token=<session_token>`.
* **Zero Client-Supplied Container Names**: The server resolves the target container strictly by inspecting the authenticated user's active session in the database.
* Full PTY emulation with terminal resize (`resize` protocol), signal handling (Ctrl+C, Ctrl+D), and interactive command tracking.

### 4. Persistent Learning Metrics vs. Disposable Sandboxes
* **Containers are Disposable**: Sandbox containers exist solely during troubleshooting. No learning state is stored inside the container filesystem.
* **Progress is Persistent**: Relational database records all user attempts, scores, durations, hints used, 4-dimensional assessment breakdown, before/after evidence metrics, and structured postmortems.
* Closing the browser, logging out, or restarting the host environment preserves all learning metrics.

### 5. 4-Dimensional State-Based Evaluation
Every submitted solution is verified against 4 distinct assessment dimensions:
1. **System State**: Verifies runtime container health, port availability, disk space, and process tree.
2. **Root Cause / Diagnosis**: Detects evidence of diagnostic commands (`ps`, `lsof`, `df`, `ss`) and hypothesis articulation.
3. **Remediation**: Validates specific corrective actions and checks for unintended side effects or service disruption.
4. **Explanation**: Assesses technical rationale, root cause explanation, fix justification, and prevention strategies.

---

## Progressive Learning Levels (25 Production Scenarios)

The lab provides 5 difficulty levels across 5 incident categories (`CPU`, `MEMORY`, `DISK`, `NETWORK`, `PERMISSIONS`):

| Level | Target Audience | Investigation Guidance | Hint Behavior | Post-Mortem Format | Scoring Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EASY** | Beginners / Linux fundamentals | Explicit guidance & suggested tools displayed | 1. Area to Inspect<br>2. Suggested Command<br>3. Targeted Resolution | **Beginner Post-Mortem** (What Happened, Commands Used, Output Meaning, Why Fix Worked) | Base 100, standard hint deductions |
| **MODERATE** | Junior transition (multi-command correlation) | Subsystem hints without direct answers | 1. Investigation Direction<br>2. Subsystem & Tool<br>3. Correlated Clue | **Junior Transition Post-Mortem** (Sequence, Evidence, Root Cause, Remediation, Validation) | Time and hint deductions |
| **FLUENT** | Realistic DevOps production incidents | Minimal guidance, self-directed commands | 1. Conceptual Direction<br>2. Hypothesis Clue<br>3. Evidence Clue | **DevOps Post-Mortem** (Methodology, Evidence, Ruled Out Causes, Remediation) | Time and hint deductions |
| **ADVANCED** | Senior cross-layer & multi-signal incidents | Multi-signal alerts, competing failure modes | 1. Broad Subsystem Direction<br>2. Signal Correlation Clue<br>3. Root Cause Clue | **Advanced SRE Post-Mortem** (Cross-Layer Correlation, Eliminated Hypotheses, Blast Radius) | **Command Efficiency Penalty** (>40 commands = -5 pts), Reasoning Bonus (+5 to +10 pts) |
| **EXPERT** | Ambiguous P0/P1 production outages | High ambiguity, stealth faults, phantom timeouts | 1. Investigation Reasoning<br>2. Diagnostic Principle<br>3. Hypothesis Elimination | **10-Point Production SRE Post-Mortem** (Summary, Impact, Detection, Hypotheses, Evidence, Root Cause, Contributing Factors, Remediation, Validation, Prevention) | **Command Efficiency Penalty** (>40 commands = -5 pts), Reasoning Bonus (+5 to +10 pts) |

---

## Security Model & Single-Host Boundaries

* **Docker Socket Mounting**: The web backend communicates with the local Docker daemon via `/var/run/docker.sock` to orchestrate isolated sandboxes.
* **Single-Host Boundary**: Mounting the Docker socket grants administrative control over the host Docker daemon. In a single-host local environment (development/self-hosted lab), this provides the necessary flexibility to dynamically spin up and tear down sandboxes.
* **Production Multi-Tenant Recommendations**: In a public multi-tenant SaaS environment:
  * Run Docker daemon in rootless mode or use user namespaces (`userns-remap`).
  * Run sandboxes inside lightweight microVMs (e.g., AWS Firecracker, Kata Containers).
  * Isolate user workloads across Kubernetes pods with dedicated network policies and gVisor/runsc runtimes.

---

## Local Setup & Quick Start

### 1. Build and Start Services
```bash
# Clone the repository
git clone <repo>
cd DevOps-Labs/linux-troubleshooting-lab

# Build and start web application and base sandbox container
docker compose up -d --build

# Verify running services
docker compose ps
```

### 2. Access the Platform
Open **`http://localhost:8088`** in your browser:
1. Click **Register** to create your personal account.
2. Select your difficulty level (`EASY` through `EXPERT`).
3. Click **Start Incident** to spawn your dedicated sandbox.
4. Troubleshoot live in the integrated browser terminal.
5. Click **Evaluate**, submit your explanation, and inspect your dimensional score and postmortem.
6. Track your progress across sessions in the **Progress** and **History** tabs.

---

## Running Automated Test Suites

The test suite validates multi-user authentication, user isolation, sandbox lifecycle, state evaluation, progressive levels, and scenario injection:

```bash
# Run all 38 tests across all test modules
python3 -m unittest discover -s tests -v

# Run multi-user auth and isolation tests specifically (16 tests)
python3 -m unittest tests/test_auth_and_isolation.py -v

# Run 4-dimensional state-based evaluation tests (8 tests)
python3 -m unittest tests/test_evaluation.py -v

# Run progressive level mechanics tests (6 tests)
python3 -m unittest tests/test_progressive_levels.py -v

# Run scenario injection & verification tests (8 tests)
python3 -m unittest tests/test_scenarios.py -v
```

---

## CLI Reference (Local Single-User Mode)

The lab can also be operated entirely via terminal CLI for local debugging:

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
