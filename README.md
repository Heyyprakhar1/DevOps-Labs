# DevOps-Labs

A curated collection of hands-on, failure-driven practice laboratories for DevOps, Cloud, and Site Reliability Engineers.

* **GitHub Repository**: [https://github.com/Heyyprakhar1/DevOps-Labs](https://github.com/Heyyprakhar1/DevOps-Labs)
* **Clone (SSH)**: `git clone git@github.com:Heyyprakhar1/DevOps-Labs.git`
* **Clone (HTTPS)**: `git clone https://github.com/Heyyprakhar1/DevOps-Labs.git`

Rather than static tutorials, walkthroughs, or read-only reference repositories, **DevOps-Labs** is designed around realistic engineering incident environments. Each lab provides an isolated sandbox where learners investigate symptoms, formulate hypotheses, gather diagnostic evidence, remediate failures, validate recovery, and write post-mortem documentation.

---

## Design Philosophy

> **"Don't just learn the command. Learn how to investigate the failure."**

Knowing utility syntax is only the starting point. Effective operational engineering requires structured troubleshooting methodology under uncertainty. Each incident across these labs exercises the core investigation lifecycle:

1. **Observe**: Detect abnormal signals, errors, and system symptoms.
2. **Form a Hypothesis**: Identify plausible subsystems and failure modes.
3. **Gather Evidence**: Probe state, logs, metrics, sockets, and configurations.
4. **Isolate the Fault**: Differentiate root cause from collateral symptoms.
5. **Remediate**: Apply targeted, minimal production fixes.
6. **Validate**: Verify service recovery and end-to-end functionality.
7. **Document the Incident**: Synthesize findings into structured post-mortem reviews.

---

## Lab Status Overview

| Lab Area | Description | Status | Directory |
| :--- | :--- | :--- | :--- |
| **Linux Troubleshooting Lab** | Browser-based, Docker-isolated Linux system & service incidents | **Available** | [`./linux-troubleshooting-lab/`](./linux-troubleshooting-lab/) |
| **Docker Labs** | Container runtime failures, bridge networking, and layer bloat | *Planned* | `docker-labs/` |
| **Kubernetes Labs** | Pod scheduling failures, CrashLoopBackOff, and CNI/DNS triage | *Planned* | `kubernetes-labs/` |
| **Terraform / IaC Labs** | State drift, dependency cycles, and plan reconciliation | *Planned* | `terraform-labs/` |
| **AWS / Cloud Labs** | IAM permission boundaries, VPC routing, and SG reachability | *Planned* | `aws-labs/` |
| **CI/CD Labs** | Pipeline breakages, credential injection, and artifact validation | *Planned* | `cicd-labs/` |
| **Observability Labs** | Prometheus alerting rules, log aggregation, and trace latency | *Planned* | `observability-labs/` |
| **DevSecOps Labs** | Container image vulnerability remediation and supply-chain auditing | *Planned* | `devsecops-labs/` |

---

## Currently Available

### [Linux Troubleshooting Lab](./linux-troubleshooting-lab/)

A browser-based, Docker-isolated Linux troubleshooting environment where learners investigate and resolve realistic production incidents using an interactive in-browser terminal (`xterm.js` over WebSockets) or a CLI.

* **Path**: [`./linux-troubleshooting-lab/`](./linux-troubleshooting-lab/)
* **Sandbox Environment**: Disposable Docker container (`linuxlab-sandbox`, hostname: `prod-app-server-01`)
* **Core Incident Coverage**:
  * **CPU**: Runaway background workers, thread starvation, and masquerading processes
  * **Memory**: Memory leaks, slab cache bloat, and OOM-killer conditions
  * **Disk & Inodes**: Unrotated debug logs, deleted open file descriptors (`lsof +L1`), and inode exhaustion
  * **Permissions**: Restrictive configuration permissions, binary ownership mismatches, and setuid issues
  * **Services**: Systemd unit boot failures, syntax errors in config, and crashloops
  * **Networking**: Port collisions (`EADDRINUSE`), socket backlogs, and loopback binds
  * **Logs & DNS**: Host resolution poisoning (`/etc/hosts`), downstream database mismatches, and connection timeouts
* **Built-in Features**:
  * Progressive hint ladder with level-adapted clues
  * Automated deterministic verification and scoring (0–100)
  * Level-specific structured post-mortems (including 10-point production SRE reviews)
  * SRE diagnostic reasoning interview practice mode

---

## Learning Model: Progressive Difficulty

Difficulty in DevOps-Labs is not measured by memorizing obscure flags or commands. Instead, difficulty scales along dimensions of **system complexity, signal ambiguity, and cognitive load**:

```
EASY ──────► MODERATE ──────► FLUENT ──────► ADVANCED ──────► EXPERT
Fundamentals    Multi-Command    Realistic       Cross-Layer      Ambiguous SRE
& Guided Tools   Correlation     Troubleshooting  Interactions     Outages
```

* **EASY**: Clear problem statements, single failure points, obvious symptoms, and suggested diagnostic tools.
* **MODERATE**: Straightforward incidents requiring multiple commands, symptom correlation, and independent tool selection.
* **FLUENT**: Realistic production incidents with minimal hand-holding; focus on authentic operational workflows.
* **ADVANCED**: Multi-signal and cross-layer incidents (e.g., host resolution interacting with configuration files; read-only mount degradation; zombie floods). Command efficiency is measured and blind brute-forcing is penalized.
* **EXPERT**: Ambiguous, production-style P0/P1 outages with conflicting symptoms, stealth processes, or delayed downstream timeouts. Requires formal hypothesis elimination and comprehensive root-cause analysis.

As difficulty increases:
* Context and explicit cues decrease
* Guidance decreases
* Ambiguity increases
* Number of interacting failure signals increases
* Required diagnostic reasoning increases
* The focus shifts from basic syntax knowledge to systematic root-cause diagnosis

---

## Conceptual Repository Structure

```text
DevOps-Labs/
├── README.md                      # Repository overview & learning model
├── linux-troubleshooting-lab/     # Available: Linux troubleshooting sandbox & Web UI
├── docker-labs/                   # Planned: Container runtime & networking triage
├── kubernetes-labs/               # Planned: Cluster incident triage & workload debugging
├── terraform-labs/                # Planned: State lock, drift, and plan remediation
├── aws-labs/                      # Planned: Cloud architecture & networking triage
├── cicd-labs/                     # Planned: Build pipeline failure & release triage
├── observability-labs/            # Planned: Telemetry, metrics, and incident alerting
└── devsecops-labs/                # Planned: Security policy, scanning, and hardening
```

*(Note: Directories labeled `# Planned` represent upcoming modules and are not yet populated.)*

---

## Getting Started

To begin practicing with the available Linux lab:

```bash
# 1. Clone the repository
git clone git@github.com:Heyyprakhar1/DevOps-Labs.git
cd DevOps-Labs/linux-troubleshooting-lab/

# 2. Review the lab-specific documentation
cat README.md

# 3. Launch the Docker sandbox
docker compose up -d

# 4. Start the interactive Web UI
pip install -r requirements.txt
python3 -m webapp
```

Then navigate to `http://localhost:8088` in your browser to start troubleshooting incidents.
