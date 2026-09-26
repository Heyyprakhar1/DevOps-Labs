import re
from typing import Dict, Any, List, Optional

class DimensionalEvaluator:
    """
    Evaluates incident resolution across four distinct dimensions:
    1. System State (Actual sandbox verification)
    2. Root Cause / Diagnosis (Identification of the underlying failure)
    3. Remediation (Appropriate targeted fix vs superficial workarounds)
    4. Explanation (Clarity, post-mortem structure, and validation explanation)
    """

    # Generic symptom phrases that indicate symptom recognition rather than root cause diagnosis
    SYMPTOM_ONLY_PATTERNS = [
        r"^i fixed (the |a )?.*(issue|problem|bug|error|thing)?\.?$",
        r"^(fixed|resolved|killed|restarted|done|it works|cleared)\.?$",
        r"^fixed (cpu|disk|memory|service|port|permission|log|network)( issue| problem)?\.?$",
        r"^i (killed|deleted|restarted|stopped) (it|the process|the service)\.?$",
        r"^disk was full\.?$",
        r"^cpu was high\.?$",
        r"^memory was full\.?$",
        r"^service was down\.?$",
    ]

    @classmethod
    def _is_symptom_only(cls, text: str) -> bool:
        """Check if explanation is merely a brief symptom observation."""
        cleaned = text.strip().lower()
        if len(cleaned) < 35:
            for pat in cls.SYMPTOM_ONLY_PATTERNS:
                if re.match(pat, cleaned):
                    return True
        return False

    @classmethod
    def _extract_scenario_entities(cls, scenario: Any) -> List[str]:
        """Extract key technical entities and keywords from scenario definition."""
        entities = []
        root_cause = getattr(scenario, "expected_root_cause", "").lower()
        fix = getattr(scenario, "expected_fix", "").lower()
        sc_id = getattr(scenario, "id", "").lower()
        category = getattr(scenario, "category", "").lower()

        # Extract quoted terms, paths, and process names
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", root_cause + " " + fix)
        for q in quoted:
            if len(q) > 2 and q not in ["none", "the", "true", "false"]:
                entities.append(q.lower())

        # Extract file paths
        paths = re.findall(r"(/[a-zA-Z0-9_\-\.\/]+)", root_cause + " " + fix)
        for p in paths:
            entities.append(p.lower())
            basename = p.split("/")[-1]
            if len(basename) > 2:
                entities.append(basename.lower())

        # Extract ports and IPs
        ports = re.findall(r"\b(8080|8000|5432|3000|127\.0\.0\.\d+|db\.internal)\b", root_cause + " " + fix)
        for pt in ports:
            entities.append(pt.lower())

        # Scenario-specific entity overrides
        specific_map = {
            "cpu_001": ["worker_loop", "tight loop", "while loop", "infinite loop"],
            "mem_001": ["mem_eater", "bytearray", "buffer", "rss"],
            "disk_001": ["transaction.log", "debug log", "truncate", "fallocate"],
            "inode_001": ["app_cache", "spool", "inode", "small files"],
            "perm_001": ["web_app.conf", "permission", "chmod", "000", "read access"],
            "easy_005": ["systemctl start", "inactive", "stopped", "web-app"],
            "service_001": ["json", "syntax error", "web_app.conf", "corrupt"],
            "net_001": ["rogue_listener", "port conflict", "8080", "address already in use"],
            "log_001": ["db.internal", "127.0.0.99", "hosts", "blackhole"],
            "mod_005": ["app.log", "ownership", "chown", "permission"],
        }
        if sc_id in specific_map:
            entities.extend(specific_map[sc_id])

        return list(set(entities))

    @classmethod
    def evaluate(
        cls,
        scenario: Any,
        is_solved: bool,
        feedback_msg: str,
        user_explanation: str = "",
        command_history: Optional[List[str]] = None,
        duration_sec: float = 0.0,
        level: str = "EASY"
    ) -> Dict[str, Any]:
        """
        Evaluate the 4 dimensions based on ground-truth system state,
        diagnostic reasoning, and written explanation.
        """
        explanation = user_explanation.strip() if user_explanation else ""
        expl_lower = explanation.lower()
        commands = command_history or []
        level_upper = level.upper()

        # ======================================================================
        # 1. SYSTEM STATE (Technical Resolution Ground Truth)
        # ======================================================================
        if is_solved:
            system_state_status = "PASS"
            system_state_detail = feedback_msg or "All sandbox verification probes passed. Healthy system state restored."
        else:
            system_state_status = "FAIL"
            system_state_detail = feedback_msg or "Sandbox verification failed: target healthy state not reached."

        # ======================================================================
        # 2. ROOT CAUSE / DIAGNOSIS
        # ======================================================================
        entities = cls._extract_scenario_entities(scenario)
        matched_entities = [e for e in entities if e in expl_lower]

        has_diag_commands = any(
            re.search(r"\b(ps|top|htop|df|du|ss|lsof|strace|grep|tail|journalctl|systemctl\s+status|find)\b", cmd.lower())
            for cmd in commands
        )

        is_symptom = cls._is_symptom_only(explanation)

        if len(matched_entities) >= 1 and len(explanation) >= 30:
            root_cause_status = "PASS"
            root_cause_detail = f"Identified specific root cause mechanism/entity ({', '.join(matched_entities[:2])})."
        elif is_symptom:
            root_cause_status = "PARTIAL/UNKNOWN" if not has_diag_commands else "PARTIAL"
            root_cause_detail = "Identified symptom, but omitted specific root-cause entity or failure mechanism."
        elif len(explanation) >= 20 and any(w in expl_lower for w in ["because", "due to", "found", "caused by", "hung", "leak", "loop", "failed"]):
            root_cause_status = "PARTIAL"
            root_cause_detail = "Troubleshooting rationale provided, but lacked detailed entity specifics."
        elif is_solved:
            if has_diag_commands:
                root_cause_status = "PARTIAL"
                root_cause_detail = "Investigation performed in terminal, but root cause not articulated in explanation."
            else:
                root_cause_status = "UNKNOWN"
                root_cause_detail = "Root cause reasoning not demonstrated in written explanation."
        else:
            root_cause_status = "FAIL"
            root_cause_detail = "Root cause was neither diagnosed nor resolved."

        # ======================================================================
        # 3. REMEDIATION
        # ======================================================================
        if is_solved:
            remediation_status = "PASS"
            remediation_detail = "Targeted remediation verified and confirmed active in container state."
        else:
            remediation_status = "FAIL"
            remediation_detail = "Remediation incomplete; required fix not reflected in container state."

        # ======================================================================
        # 4. EXPLANATION
        # ======================================================================
        if len(explanation) == 0:
            explanation_status = "NEEDS IMPROVEMENT"
            explanation_detail = "No explanation submitted."
        elif len(explanation) < 35 or is_symptom:
            explanation_status = "NEEDS IMPROVEMENT"
            explanation_detail = "Explanation is too brief to demonstrate diagnostic methodology and validation."
        elif len(explanation) < (100 if level_upper in ["ADVANCED", "EXPERT"] else 70):
            explanation_status = "PARTIAL"
            explanation_detail = "Basic explanation provided. Include root cause discovery and validation steps for complete grading."
        else:
            explanation_status = "PASS"
            explanation_detail = "Clear and structured explanation covering diagnosis, remediation, and verification."

        # ======================================================================
        # OVERALL VERDICT & EXPLANATION FEEDBACK
        # ======================================================================
        technical_resolution = "PASS" if is_solved else "FAIL"
        overall_verdict = "INCIDENT RESOLVED" if is_solved else "INCIDENT UNRESOLVED"

        if is_solved:
            if explanation_status in ["NEEDS IMPROVEMENT", "PARTIAL"]:
                explanation_feedback = (
                    "Your system is in the expected healthy state, but your explanation "
                    "does not demonstrate the troubleshooting reasoning clearly."
                )
            else:
                explanation_feedback = (
                    "Incident resolved successfully with verified healthy container state "
                    "and comprehensive diagnostic reasoning."
                )
        else:
            explanation_feedback = (
                f"Incident unresolved: {feedback_msg or 'The container state does not match expected healthy conditions. Review symptoms and retry.'}"
            )

        return {
            "technical_resolution": technical_resolution,
            "overall_verdict": overall_verdict,
            "overall_message": explanation_feedback if is_solved else (feedback_msg or "Incident unresolved."),
            "explanation_feedback": explanation_feedback,
            "dimensions": {
                "system_state": {
                    "name": "System State",
                    "status": system_state_status,
                    "detail": system_state_detail,
                },
                "root_cause": {
                    "name": "Root Cause",
                    "status": root_cause_status,
                    "detail": root_cause_detail,
                },
                "remediation": {
                    "name": "Remediation",
                    "status": remediation_status,
                    "detail": remediation_detail,
                },
                "explanation": {
                    "name": "Explanation",
                    "status": explanation_status,
                    "detail": explanation_detail,
                },
            }
        }
