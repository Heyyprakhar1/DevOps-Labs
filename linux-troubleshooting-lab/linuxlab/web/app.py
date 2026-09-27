import time
import os
import uuid
import random
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, WebSocket, HTTPException, Body, Request, Response, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from linuxlab.config import CATEGORIES, DIFFICULTIES, LEVELS, LEVEL_DESCRIPTIONS, CONTAINER_NAME
from linuxlab.lab.controller import LabController
from linuxlab.lab.health import check_lab_health
from linuxlab.lab.reset import reset_lab
from linuxlab.lab.container_manager import SandboxManager
from linuxlab.scenarios.registry import registry
from linuxlab.state.manager import StateManager
from linuxlab.evaluation.scoring import IncidentScorer
from linuxlab.evaluation.reports import IncidentReportGenerator
from linuxlab.evaluation.evaluator import IncidentEvaluator
from linuxlab.evaluation.evidence import EvidenceCollector
from linuxlab.ai.ollama import OllamaClient
from linuxlab.interview.questions import INTERVIEW_SCENARIOS, get_interview_scenarios_for_level
from linuxlab.web.terminal import TerminalSession
from linuxlab.db import db
from linuxlab import auth

logger = logging.getLogger("linuxlab.web")

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

app = FastAPI(title="Linux Troubleshooting Lab", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

default_controller = LabController(CONTAINER_NAME)
ai_client = OllamaClient()

# Startup lifecycle: initialize DB and cleanup orphaned sandboxes
@app.on_event("startup")
async def on_startup():
    db.init_db()
    try:
        SandboxManager.cleanup_orphaned_sandboxes()
    except Exception as e:
        logger.warning(f"Startup sandbox cleanup: {e}")

# Request Models
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

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

# --- Authentication Helpers & Dependencies ---

async def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency: Extract and validate user from Bearer header, X-Session-Token, cookie, or query param."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.headers.get("X-Session-Token"):
        token = request.headers.get("X-Session-Token").strip()
    elif "session_token" in request.cookies:
        token = request.cookies.get("session_token")
    elif "token" in request.query_params:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = auth.get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user

async def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """Dependency: Resolve user if token is provided, or return None."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None

# --- Static Frontend ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
@app.head("/")
async def get_index():
    return FileResponse(str(INDEX_FILE))

# --- Authentication Endpoints ---

@app.post("/api/auth/register")
async def api_register(req: RegisterRequest, response: Response):
    """Register a new user and return session token."""
    try:
        user = auth.register_user(req.username, req.password)
        token = db.create_auth_session(user["id"])
        response.set_cookie(
            key="session_token",
            value=token,
            max_age=7 * 24 * 3600,
            httponly=False,
            samesite="lax"
        )
        return {
            "status": "ok",
            "message": "User registered successfully.",
            "user": {"id": user["id"], "username": user["username"]},
            "token": token
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed.")

@app.post("/api/auth/login")
async def api_login(req: LoginRequest, response: Response):
    """Authenticate user credentials and create session token."""
    try:
        user, token = auth.login_user(req.username, req.password)
        response.set_cookie(
            key="session_token",
            value=token,
            max_age=7 * 24 * 3600,
            httponly=False,
            samesite="lax"
        )
        return {
            "status": "ok",
            "message": "Login successful.",
            "user": user,
            "token": token
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed.")

@app.post("/api/auth/logout")
async def api_logout(request: Request, response: Response, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Log out user and invalidate session token."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.headers.get("X-Session-Token"):
        token = request.headers.get("X-Session-Token").strip()
    elif "session_token" in request.cookies:
        token = request.cookies.get("session_token")

    if token:
        auth.logout_user(token)

    response.delete_cookie("session_token")
    return {"status": "ok", "message": "Logged out successfully."}

@app.get("/api/auth/me")
async def api_get_current_user(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return profile data of currently authenticated user."""
    active_session = db.get_active_incident_session(current_user["id"])
    return {
        "authenticated": True,
        "user": current_user,
        "has_active_incident": active_session is not None,
        "active_incident_id": active_session.get("scenario_id") if active_session else None
    }

# --- Incident Lifecycle & Status Endpoints ---

def _format_unlocked_hints(scenario, hints_used: List[int], sc_level: str) -> List[Dict[str, Any]]:
    penalties = {1: 5, 2: 10, 3: 15}
    hint_type_labels = {
        "EASY": {1: "Area to Inspect", 2: "Suggested Command", 3: "Targeted Resolution"},
        "MODERATE": {1: "Investigation Direction", 2: "Subsystem & Tool", 3: "Correlated Clue"},
        "FLUENT": {1: "Conceptual Direction", 2: "Hypothesis Clue", 3: "Evidence Clue"},
        "ADVANCED": {1: "Broad Subsystem Direction", 2: "Signal Correlation Clue", 3: "Root Cause Clue"},
        "EXPERT": {1: "Investigation Reasoning", 2: "Diagnostic Principle", 3: "Hypothesis Elimination Guidance"},
    }
    unlocked = []
    for h_lvl in sorted(hints_used):
        if 1 <= h_lvl <= len(scenario.hints):
            unlocked.append({
                "level": h_lvl,
                "type_label": hint_type_labels.get(sc_level, {}).get(h_lvl, f"Hint #{h_lvl}"),
                "hint": scenario.hints[h_lvl - 1],
                "penalty": penalties.get(h_lvl, 10),
            })
    return unlocked

@app.get("/api/status")
async def get_status(user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Get system health and user-specific active incident status."""
    active_incident = None

    if user:
        # Check user-specific active session in DB
        session = db.get_active_incident_session(user["id"])
        if session:
            sc = registry.get(session.get("scenario_id"))
            if sc:
                elapsed = max(0, int(time.time() - session.get("start_time", time.time())))
                sc_level = getattr(sc, "level", sc.difficulty).upper()
                hints_used = session.get("hints_used", [])
                active_incident = {
                    "id": sc.id,
                    "category": sc.category.upper(),
                    "difficulty": sc.difficulty,
                    "level": sc_level,
                    "title": sc.title,
                    "symptoms": sc.symptoms,
                    "context": sc.context,
                    "objective": sc.objective,
                    "hints_used": hints_used,
                    "unlocked_hints": _format_unlocked_hints(sc, hints_used, sc_level),
                    "command_history": session.get("command_history", []),
                    "elapsed_seconds": elapsed,
                    "container_name": session.get("container_name"),
                }
        health_ctrl = LabController(session["container_name"]) if session else default_controller
        health = check_lab_health(health_ctrl)
    else:
        # Legacy/anonymous fallback
        session = StateManager.get_session()
        if session:
            sc = registry.get(session.get("scenario_id"))
            if sc:
                elapsed = max(0, int(time.time() - session.get("start_time", time.time())))
                sc_level = getattr(sc, "level", sc.difficulty).upper()
                hints_used = session.get("hints_used", [])
                active_incident = {
                    "id": sc.id,
                    "category": sc.category.upper(),
                    "difficulty": sc.difficulty,
                    "level": sc_level,
                    "title": sc.title,
                    "symptoms": sc.symptoms,
                    "context": sc.context,
                    "objective": sc.objective,
                    "hints_used": hints_used,
                    "unlocked_hints": _format_unlocked_hints(sc, hints_used, sc_level),
                    "command_history": session.get("command_history", []),
                    "elapsed_seconds": elapsed,
                }
        health = check_lab_health(default_controller)

    return {
        "sandbox": health,
        "active_incident": active_incident,
        "levels": LEVELS,
        "level_descriptions": LEVEL_DESCRIPTIONS,
        "user": user,
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
async def start_random_incident(
    req: RandomIncidentRequest = Body(default=RandomIncidentRequest()),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generate and inject a random incident into a user's isolated Docker sandbox."""
    user_id = current_user["id"]
    recent_attempts = db.get_user_attempts(user_id, limit=3)
    recent_ids = [a["scenario_id"] for a in recent_attempts]
    target_level = req.level or req.difficulty

    scenario = registry.get_random(
        recent_ids=recent_ids,
        category=req.category,
        difficulty=req.difficulty,
        level=target_level
    )

    if not scenario:
        raise HTTPException(status_code=404, detail="No matching scenarios found for the selected criteria.")

    # 1. Clean up any previous sandbox for this user
    SandboxManager.cleanup_user_sandboxes(user_id)

    # 2. Create a new dedicated, isolated sandbox container with resource limits
    session_id = str(uuid.uuid4())
    container_name = SandboxManager.create_sandbox(user_id, session_id)
    user_ctrl = LabController(container_name)

    # 3. Inject fault into the isolated sandbox
    injected = scenario.setup(user_ctrl)
    if not injected:
        SandboxManager.destroy_sandbox(container_name)
        raise HTTPException(status_code=500, detail="Failed to inject incident fault into container.")

    # 4. Capture baseline evidence and persist active session
    initial_evidence = EvidenceCollector.capture(user_ctrl, scenario)
    sc_level = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()
    db.create_incident_session(
        user_id=user_id,
        scenario_id=scenario.id,
        container_name=container_name,
        level=sc_level,
        initial_evidence=initial_evidence
    )

    return {
        "status": "injected",
        "incident": scenario.get_briefing(),
        "container_name": container_name,
        "start_time": time.time(),
    }

@app.post("/api/incidents/{scenario_id}/start")
async def start_specific_incident(
    scenario_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Inject a specific scenario into a user's isolated Docker sandbox."""
    user_id = current_user["id"]
    scenario = registry.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")

    # 1. Clean up any previous sandbox for this user
    SandboxManager.cleanup_user_sandboxes(user_id)

    # 2. Create isolated container with resource limits
    session_id = str(uuid.uuid4())
    container_name = SandboxManager.create_sandbox(user_id, session_id)
    user_ctrl = LabController(container_name)

    # 3. Inject fault
    injected = scenario.setup(user_ctrl)
    if not injected:
        SandboxManager.destroy_sandbox(container_name)
        raise HTTPException(status_code=500, detail="Failed to inject incident fault into container.")

    # 4. Capture baseline evidence and persist session
    initial_evidence = EvidenceCollector.capture(user_ctrl, scenario)
    sc_level = getattr(scenario, "level", getattr(scenario, "difficulty", "EASY")).upper()
    db.create_incident_session(
        user_id=user_id,
        scenario_id=scenario.id,
        container_name=container_name,
        level=sc_level,
        initial_evidence=initial_evidence
    )

    return {
        "status": "injected",
        "incident": scenario.get_briefing(),
        "container_name": container_name,
        "start_time": time.time(),
    }

@app.post("/api/incidents/hint")
async def get_hint(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve next progressive hint for the user's active incident."""
    user_id = current_user["id"]
    session = db.get_active_incident_session(user_id)
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
    db.record_hint_to_session(user_id, next_level)

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
        "hints_used": hints_used + [next_level],
    }

@app.post("/api/incidents/evaluate")
async def evaluate_incident(
    req: EvaluateRequest = Body(default=EvaluateRequest()),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Evaluate actual container state of user's sandbox and return 4-dimensional assessment."""
    user_id = current_user["id"]
    session = db.get_active_incident_session(user_id)
    if not session:
        raise HTTPException(status_code=400, detail="No active incident session to evaluate.")

    scenario = registry.get(session.get("scenario_id"))
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    container_name = session.get("container_name")
    user_ctrl = LabController(container_name)
    user_evaluator = IncidentEvaluator(user_ctrl)

    explanation = req.explanation.strip() if req.explanation else ""
    # Inject user_id into session dict so evaluator records to persistent DB
    session["user_id"] = user_id

    eval_result = user_evaluator.evaluate_session(session, scenario, user_explanation=explanation)
    eval_result.pop("scenario", None)

    # If incident is solved, clean up sandbox container and mark session completed
    if eval_result.get("is_solved"):
        try:
            SandboxManager.destroy_sandbox(container_name)
        except Exception as e:
            logger.warning(f"Error cleaning up sandbox after evaluation: {e}")

    return eval_result

@app.post("/api/incidents/reset")
async def reset_environment(current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Abandon active incident session and destroy user's isolated sandbox, or reset baseline container."""
    if current_user:
        user_id = current_user["id"]
        session = db.get_active_incident_session(user_id)
        if session:
            container_name = session.get("container_name")
            if container_name:
                SandboxManager.destroy_sandbox(container_name)
            db.close_incident_session(user_id, status="abandoned")

        return {
            "success": True,
            "message": "Incident session closed and sandbox container removed."
        }
    else:
        success = reset_lab(default_controller)
        StateManager.clear_session()
        health = check_lab_health(default_controller)
        return {
            "success": success,
            "sandbox": health,
            "message": "Lab environment reset complete and baseline services active." if success else "Reset encountered an issue."
        }

# --- Progress & History Endpoints ---

@app.get("/api/progress")
async def get_progress(user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """Return aggregated progress metrics for the authenticated user, or global fallback."""
    if user:
        return db.calculate_user_progress(user["id"])
    return StateManager.calculate_progress()

@app.get("/api/history")
async def get_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Return list of past incident attempts strictly for the authenticated user."""
    return db.get_user_attempts(current_user["id"], limit=50)

@app.get("/api/history/{attempt_id}")
async def get_history_detail(
    attempt_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieve full evaluation and postmortem details for a specific attempt (ownership verified)."""
    attempt = db.get_user_attempt(attempt_id, current_user["id"])
    if not attempt:
        raise HTTPException(status_code=404, detail="Incident attempt record not found.")
    return attempt

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

# --- WebSocket Terminal with Strict User Sandbox Authorization ---

@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, token: Optional[str] = Query(default=None)):
    """Interactive WebSocket endpoint attached to container bash PTY.
    Strictly binds to the authenticated user's isolated sandbox container.
    """
    await websocket.accept()

    # Determine user identity from query token or cookie
    resolved_token = token
    if not resolved_token:
        resolved_token = websocket.cookies.get("session_token")

    user = None
    if resolved_token:
        user = auth.get_user_from_token(resolved_token)

    container_name = CONTAINER_NAME
    user_id = None

    if user:
        user_id = user["id"]
        active_session = db.get_active_incident_session(user_id)
        if not active_session:
            await websocket.send_text(
                "\r\n\x1b[33m[No active incident session. Please select or start an incident first.]\x1b[0m\r\n"
            )
            await websocket.close()
            return
        container_name = active_session["container_name"]
    else:
        # Unauthenticated: If legacy base container is running, allow connection (dev/testing)
        if not default_controller.is_running():
            await websocket.send_text(
                "\r\n\x1b[31m[Authentication required. Please sign in to launch an isolated sandbox.]\x1b[0m\r\n"
            )
            await websocket.close()
            return

    terminal_session = TerminalSession(websocket, container_name=container_name, user_id=user_id)
    try:
        await terminal_session.run()
    except Exception as e:
        logger.debug(f"Terminal session closed: {e}")
