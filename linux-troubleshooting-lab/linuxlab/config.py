import os
from pathlib import Path

# Base Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.getenv("LINUXLAB_STATE_DIR", ROOT_DIR / "linuxlab" / "state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_FILE = STATE_DIR / "history.json"
SESSION_FILE = STATE_DIR / "current_session.json"
DB_FILE = STATE_DIR / "linuxlab.db"

# Docker Configuration
CONTAINER_NAME = os.getenv("LINUXLAB_CONTAINER_NAME", "linuxlab-sandbox")
IMAGE_NAME = os.getenv("LINUXLAB_IMAGE", "linuxlab-sandbox:latest")
COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"

# AI / Ollama Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

# Categories Supported
CATEGORIES = [
    "cpu",
    "memory",
    "disk",
    "inodes",
    "permissions",
    "services",
    "networking",
    "logs",
]

# Levels & Difficulties Supported
LEVELS = ["EASY", "MODERATE", "FLUENT", "ADVANCED", "EXPERT"]

LEVEL_DESCRIPTIONS = {
    "EASY": "Linux fundamentals + guided troubleshooting",
    "MODERATE": "Multi-command diagnosis & straightforward incidents",
    "FLUENT": "Realistic troubleshooting with limited guidance",
    "ADVANCED": "Multi-signal & cross-layer incident correlation",
    "EXPERT": "Ambiguous production-style SRE incident resolution",
}

DIFFICULTIES = LEVELS + ["MEDIUM", "2YOE", "HARD", "PRODUCTION"]
