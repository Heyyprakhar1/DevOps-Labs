from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

class IncidentReportGenerator:
    """Generates structured, level-aware post-mortem and evaluation reports."""

    @classmethod
    def get_structured_sections(cls, scenario: Any) -> Dict[str, Any]:
        """Generate structured breakdown matching the learning level."""
        level = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()
        custom = getattr(scenario, "postmortem_sections", {}) or {}

        if level == "EASY":
            return {
                "level": "EASY",
                "title": "Beginner Learning Post-Mortem",
                "sections": {
                    "What Happened": custom.get("what_happened", scenario.expected_root_cause),
                    "Commands Used": custom.get("commands_used", ", ".join(getattr(scenario, "expected_tools", []))),
                    "What Output Meant": custom.get("output_meaning", "Diagnostic command output revealed the system bottleneck or error."),
                    "Why Fix Worked": custom.get("why_fix_worked", scenario.expected_fix),
                }
            }

        elif level == "MODERATE":
            return {
                "level": "MODERATE",
                "title": "Junior Transition Post-Mortem",
                "sections": {
                    "Investigation Sequence": custom.get("investigation_sequence", "System status -> Log analysis -> Subsystem inspection -> Remediation."),
                    "Evidence Collected": custom.get("evidence", f"Root cause signal: {scenario.expected_root_cause}"),
                    "Root Cause": scenario.expected_root_cause,
                    "Remediation": scenario.expected_fix,
                    "Validation Steps": getattr(scenario, "validation", "Verified service recovery with health checks."),
                }
            }

        elif level == "FLUENT":
            return {
                "level": "FLUENT",
                "title": "DevOps Incident Post-Mortem",
                "sections": {
                    "Troubleshooting Methodology": custom.get("methodology", "Symptom observation -> Hypothesis formation -> Evidence validation -> Targeted fix."),
                    "Evidence & Root Cause": custom.get("evidence", scenario.expected_root_cause),
                    "Why Alternative Causes Were Ruled Out": custom.get("ruled_out", "Superficial metrics ruled out once subsystem-level probes were executed."),
                    "Remediation & Prevention": f"Fix: {scenario.expected_fix}. Prevention: {custom.get('prevention', 'Add health checks and config validation.')}",
                }
            }

        elif level == "ADVANCED":
            return {
                "level": "ADVANCED",
                "title": "Advanced SRE Cross-Layer Post-Mortem",
                "sections": {
                    "Signal Correlation Across Layers": custom.get("signal_correlation", "Correlated host telemetry with application runtime errors across multiple boundaries."),
                    "Elimination of Hypotheses": custom.get("eliminated_hypotheses", "Systematically ruled out competing failure modes before applying fix."),
                    "Root Cause & Blast Radius": f"Root Cause: {scenario.expected_root_cause}. Blast Radius: {custom.get('blast_radius', 'Service unavailability.')}",
                    "Production Remediation": scenario.expected_fix,
                    "Validation": getattr(scenario, "validation", "End-to-end verification via automated probes."),
                }
            }

        else:  # EXPERT - 10-Point Production Postmortem
            return {
                "level": "EXPERT",
                "title": "Production Incident Review (SRE Post-Mortem)",
                "sections": {
                    "1. Incident Summary": custom.get("incident_summary", scenario.title),
                    "2. Impact": custom.get("impact", "High-severity production degradation."),
                    "3. Detection": custom.get("detection", "Prometheus alerts and user synthetic monitors."),
                    "4. Initial Hypotheses": custom.get("initial_hypotheses", "1. Process deadlock; 2. Saturated socket; 3. Configuration drift."),
                    "5. Evidence Collected": custom.get("evidence_collected", f"Subsystem artifacts confirmed: {scenario.expected_root_cause}"),
                    "6. Root Cause": scenario.expected_root_cause,
                    "7. Contributing Factors": custom.get("contributing_factors", "Incomplete validation and missing automated rollback guards."),
                    "8. Remediation": scenario.expected_fix,
                    "9. Validation": custom.get("validation", getattr(scenario, "validation", "Full transactional verification.")),
                    "10. Prevention / Follow-up Actions": custom.get("prevention", "Implement canary deployments, tighter resource quotas, and telemetry alerts.")
                }
            }

    @classmethod
    def format_report(
        cls,
        scenario: Any,
        is_solved: bool,
        score_data: Dict[str, Any],
        user_explanation: str = "",
        ai_critique: str = "",
        dimensional_data: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None
    ) -> str:
        verdict = "INCIDENT RESOLVED" if is_solved else "INCIDENT UNRESOLVED"
        status_str = f"[bold green]✔ {verdict}[/bold green]" if is_solved else f"[bold red]✘ {verdict}[/bold red]"
        score = score_data.get("score", 0)
        level = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()

        dur_sec = score_data.get("duration_sec", 0)
        minutes = int(dur_sec // 60)
        seconds = int(dur_sec % 60)
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        hints_count = score_data.get("hints_count", 0)
        hint_deduction = score_data.get("hint_deduction", 0)

        report_lines = [
            f"[bold cyan]Incident:[/bold cyan] {scenario.title} ({scenario.id})",
            f"[bold cyan]Category:[/bold cyan] {scenario.category.upper()}  |  [bold cyan]Level:[/bold cyan] [bold yellow]{level}[/bold yellow]",
            f"[bold cyan]Overall Verdict:[/bold cyan] {status_str}",
            f"[bold cyan]Time to Resolution:[/bold cyan] {time_str}",
            f"[bold cyan]Hints Used:[/bold cyan] {hints_count} (-{hint_deduction} pts)",
            f"[bold cyan]Score:[/bold cyan] [bold yellow]{score}/100[/bold yellow]\n",
        ]

        # Four Dimensions
        dims = (dimensional_data or {}).get("dimensions", {})
        if dims:
            report_lines.append("[bold cyan underline]=== EVALUATION DIMENSIONS ===[/bold cyan underline]")
            dim_order = ["system_state", "root_cause", "remediation", "explanation"]
            dim_labels = {
                "system_state": "Technical Resolution",
                "root_cause": "Root Cause / Diagnosis",
                "remediation": "Remediation Applied",
                "explanation": "Explanation Quality"
            }
            for d_key in dim_order:
                if d_key in dims:
                    item = dims[d_key]
                    st = item.get("status", "PASS")
                    color = "green" if st == "PASS" else ("yellow" if "PARTIAL" in st else ("cyan" if st == "UNKNOWN" else "red"))
                    label = dim_labels.get(d_key, item.get("name", d_key))
                    report_lines.append(f"  • [bold white]{label}:[/bold white] [{color}]{st}[/{color}] - {item.get('detail', '')}")
            report_lines.append("")

        # Explanation Feedback Callout
        feedback = (dimensional_data or {}).get("explanation_feedback", "")
        if feedback:
            report_lines.extend([
                "[bold white underline]Evaluation Feedback:[/bold white underline]",
                f"[italic]{feedback}[/italic]\n"
            ])

        # Machine Evidence Summary
        if evidence and "summary" in evidence:
            report_lines.append("[bold cyan underline]=== MACHINE VERIFICATION EVIDENCE ===[/bold cyan underline]")
            for item in evidence.get("summary", []):
                metric = item.get("metric", "")
                before_val = item.get("before", "")
                after_val = item.get("after", "")
                status_val = item.get("status", "")
                color = "green" if status_val in ["PASS", "HEALTHY", "RESOLVED", "IMPROVED"] else "red"
                report_lines.append(f"  • [bold white]{metric}:[/bold white] {before_val} ➜ [bold {color}]{after_val}[/bold {color}] ([{color}]{status_val}[/{color}])")
            report_lines.append("")

        structured = cls.get_structured_sections(scenario)
        report_lines.append(f"[bold magenta underline]=== {structured['title'].upper()} ===[/bold magenta underline]")
        for header, content in structured["sections"].items():
            report_lines.append(f"[bold white]{header}:[/bold white]\n{content}\n")

        if user_explanation.strip():
            report_lines.extend([
                "[bold white underline]Your Diagnostic Explanation:[/bold white underline]",
                f'"{user_explanation.strip()}"\n'
            ])

        if ai_critique.strip():
            report_lines.extend([
                "[bold magenta underline]AI Senior SRE Feedback:[/bold magenta underline]",
                f"{ai_critique.strip()}\n"
            ])

        report_lines.extend([
            "[bold white underline]Key DevOps Learning Points:[/bold white underline]"
        ])
        for pt in getattr(scenario, "learning_points", []):
            report_lines.append(f"  • {pt}")

        return "\n".join(report_lines)

    @classmethod
    def print_report(
        cls,
        scenario: Any,
        is_solved: bool,
        score_data: Dict[str, Any],
        user_explanation: str = "",
        ai_critique: str = "",
        dimensional_data: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None
    ):
        body = cls.format_report(
            scenario=scenario,
            is_solved=is_solved,
            score_data=score_data,
            user_explanation=user_explanation,
            ai_critique=ai_critique,
            dimensional_data=dimensional_data,
            evidence=evidence
        )
        title = "LINUX INCIDENT POST-MORTEM & EVALUATION"
        border_style = "green" if is_solved else "red"
        console.print(Panel(body, title=f"[bold]{title}[/bold]", border_style=border_style, expand=False))
