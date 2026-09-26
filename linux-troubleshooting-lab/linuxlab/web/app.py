import time
import os
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, WebSocket, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from linuxlab.config import CATEGORIES, DIFFICULTIES, LEVELS, LEVEL_DESCRIPTIONS
from linuxlab.lab.controller import LabController
from linuxlab.lab.health import check_lab_health
from linuxlab.lab.reset import reset_lab
from linuxlab.scenarios.registry import registry
from linuxlab.state.manager import StateManager
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.evaluation.reports import IncidentReportGenerator
from linuxlab.evaluation.evaluator import IncidentEvaluator
from linuxlab.evaluation.evidence import EvidenceCollector
from linuxlab.ai.ollama import OllamaClient
from linuxlab.interview.questions import INTERVIEW_SCENARIOS, get_interview_scenarios_for_level
from linuxlab.web.terminal import TerminalSession

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

app = FastAPI(title="Linux Troubleshooting Lab", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

controller = LabController()
evaluator = IncidentEvaluator(controller)
ai_client = OllamaClient()

# Request Models
class RandomIncidentRequest(BaseModel):
    category: Optional[str] = None
    difficulty: Optional[str] = None
    level: Optional[str] = None

class EvaluateRequest(BaseModel):
    explanation: Optional[str] = ""

class InterviewEvaluateRequest(BaseModel):
    question_id: str
    initial_answer: str
    follow_up_answers: List[str] = []

# --- Static Frontend ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
@app.head("/")
async def get_index():
    return FileResponse(str(INDEX_FILE))

# --- API Endpoints ---

@app.get("/api/status")
async def get_status():
    """Get system and lab container status along with active session data and level metadata."""
    health = check_lab_health(controller)
    session = StateManager.get_session()
    active_incident = None

    if session:
        sc = registry.get(session.get("scenario_id"))
        if sc:
            elapsed = max(0, int(time.time() - session.get("start_time", time.time())))
            sc_level = getattr(sc, "level", sc.difficulty).upper()
            active_incident = {
                "id": sc.id,
                "category": sc.category.upper(),
                "difficulty": sc.difficulty,
                "level": sc_level,
                "title": sc.title,
                "symptoms": sc.symptoms,
                "context": sc.context,
                "objective": sc.objective,
                "investigation_guidance": getattr(sc, "investigation_guidance", ""),
                "expected_tools": getattr(sc, "expected_tools", []),
                "hints_used": session.get("hints_used", []),
                "command_history": session.get("command_history", []),
                "elapsed_seconds": elapsed,
            }

    return {
        "sandbox": health,
        "active_incident": active_incident,
        "levels": LEVELS,
        "level_descriptions": LEVEL_DESCRIPTIONS,
    }

@app.get("/api/scenarios")
async def get_scenarios(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    level: Optional[str] = None
):
    """List all registered scenarios, filtered by category, difficulty, or level."""
    scenarios = registry.filter(category=category, difficulty=difficulty, level=level)
    return [
        {
            "id": s.id,
            "category": s.category.upper(),
            "difficulty": s.difficulty,
            "level": getattr(s, "level", s.difficulty).upper(),
            "title": s.title,
            "symptoms": s.symptoms,
            "objective": s.objective,
            "expected_tools": getattr(s, "expected_tools", []),
        }
        for s in scenarios
    ]

@app.post("/api/incidents/random")
async def start_random_incident(req: RandomIncidentRequest = Body(default=RandomIncidentRequest())):
    """Generate and inject a random incident filtered by level into the lab container."""
    controller.ensure_running()
    controller.reset()

    recent_ids = StateManager.get_recent_scenario_ids(count=3)
    target_level = req.level or req.difficulty

    scenario = registry.get_random(
        recent_ids=recent_ids,
        category=req.category,
        difficulty=req.difficulty,
        level=target_level
    )

    if not scenario:
        raise HTTPException(status_code=404, detail="No matching scenarios found for the selected criteria.")

    injected = scenario.setup(controller)
    if not injected:
        raise HTTPException(status_code=500, detail="Failed to inject incident fault into container.")

    initial_evidence = EvidenceCollector.capture(controller, scenario)
    StateManager.start_session(scenario.id, initial_evidence=initial_evidence)
    return {
        "status": "injected",
        "incident": scenario.get_briefing(),
        "start_time": time.time(),
    }

@app.post("/api/incidents/{scenario_id}/start")
async def start_specific_incident(scenario_id: str):
    """Inject a specific scenario by its ID."""
    controller.ensure_running()
    controller.reset()

    scenario = registry.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")

    injected = scenario.setup(controller)
    if not injected:
        raise HTTPException(status_code=500, detail="Failed to inject incident fault into container.")

    initial_evidence = EvidenceCollector.capture(controller, scenario)
    StateManager.start_session(scenario.id, initial_evidence=initial_evidence)
    return {
        "status": "injected",
        "incident": scenario.get_briefing(),
        "start_time": time.time(),
    }

@app.post("/api/incidents/hint")
async def get_hint():
    """Retrieve next progressive hint for the active incident with level-adapted labels."""
    session = StateManager.get_session()
    if not session:
        raise HTTPException(status_code=400, detail="No active incident session.")

    scenario = registry.get(session.get("scenario_id"))
    if not scenario:
        raise HTTPException(status_code=404, detail="Active scenario not found.")

    hints_used = session.get("hints_used", [])
    next_level = len(hints_used) + 1

    if next_level > len(scenario.hints):
        return {
            "exhausted": True,
            "message": "All available hints have already been revealed.",
            "hints": scenario.hints,
            "hints_used": hints_used,
        }

    hint_text = scenario.hints[next_level - 1]
    StateManager.record_hint(next_level)

    penalties = {1: 5, 2: 10, 3: 15}
    sc_level = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()

    hint_type_labels = {
        "EASY": {1: "Area to Inspect", 2: "Suggested Command", 3: "Targeted Resolution"},
        "MODERATE": {1: "Investigation Direction", 2: "Subsystem & Tool", 3: "Correlated Clue"},
        "FLUENT": {1: "Conceptual Direction", 2: "Hypothesis Clue", 3: "Evidence Clue"},
        "ADVANCED": {1: "Broad Subsystem Direction", 2: "Signal Correlation Clue", 3: "Root Cause Clue"},
        "EXPERT": {1: "Investigation Reasoning", 2: "Diagnostic Principle", 3: "Hypothesis Elimination Guidance"},
    }
    type_label = hint_type_labels.get(sc_level, {}).get(next_level, f"Hint #{next_level}")

    return {
        "exhausted": False,
        "level": next_level,
        "type_label": type_label,
        "hint": hint_text,
        "penalty": penalties.get(next_level, 10),
        "hints_used": session.get("hints_used", []) + [next_level],
    }

@app.post("/api/incidents/evaluate")
async def evaluate_incident(req: EvaluateRequest = Body(default=EvaluateRequest())):
    """Evaluate actual container state and return 4-dimensional evaluation with machine evidence."""
    session = StateManager.get_session()
    if not session:
        raise HTTPException(status_code=400, detail="No active incident session to evaluate.")

    scenario = registry.get(session.get("scenario_id"))
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    explanation = req.explanation.strip() if req.explanation else ""
    eval_result = evaluator.evaluate_session(session, scenario, user_explanation=explanation)
    # Ensure scenario instance is not in JSON response
    eval_result.pop("scenario", None)
    return eval_result

@app.post("/api/incidents/reset")
async def reset_environment():
    """Reset lab container to clean baseline and clear active session."""
    success = reset_lab(controller)
    health = check_lab_health(controller)
    return {
        "success": success,
        "sandbox": health,
        "message": "Lab environment reset complete and baseline services active." if success else "Reset encountered an issue."
    }

@app.get("/api/progress")
async def get_progress():
    """Return aggregated progress metrics, category stats, and progressive level mastery."""
    return StateManager.calculate_progress()

# --- Interview Mode API ---

@app.get("/api/interview/random")
async def get_interview_question(level: Optional[str] = None):
    """Get a random SRE troubleshooting interview question, optionally filtered by level."""
    scenarios = get_interview_scenarios_for_level(level)
    sc = random.choice(scenarios)
    return {
        "id": sc["id"],
        "level": sc.get("level", "FLUENT"),
        "topic": sc["topic"],
        "initial_prompt": sc["initial_prompt"],
        "follow_ups": sc["follow_ups"],
    }

@app.post("/api/interview/evaluate")
async def evaluate_interview(req: InterviewEvaluateRequest):
    """Evaluate interview responses and return senior SRE benchmark."""
    sc = next((s for s in INTERVIEW_SCENARIOS if s["id"] == req.question_id), None)
    if not sc:
        raise HTTPException(status_code=404, detail="Interview question not found.")

    ai_eval = None
    if ai_client.is_available() and req.initial_answer.strip():
        transcript = f"Question: {sc['initial_prompt']}\nCandidate Answer: {req.initial_answer}\n"
        for i, ans in enumerate(req.follow_up_answers):
            fq = sc["follow_ups"][i] if i < len(sc["follow_ups"]) else f"Follow-up #{i+1}"
            transcript += f"{fq}\nAnswer: {ans}\n"
        prompt = (
            f"{transcript}\n"
            "Evaluate the candidate's answers as a Senior Staff SRE interviewer. "
            "Highlight: 1. Strong reasoning points. 2. Misconceptions or gaps. 3. Final rating."
        )
        ai_eval = ai_client.generate(prompt, system="You are an expert SRE interview evaluator.")

    return {
        "sre_breakdown": sc["sre_breakdown"],
        "ai_evaluation": ai_eval,
    }

# --- WebSocket Terminal ---

@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """Interactive WebSocket endpoint attached to container bash PTY."""
    await websocket.accept()
    terminal_session = TerminalSession(websocket)
    try:
        await terminal_session.run()
    except Exception as e:
        logger.debug(f"Terminal session closed: {e}")
