import re
import bcrypt
from typing import Optional, Dict, Any, Tuple
from linuxlab.db import db

def hash_password(password: str) -> str:
    """Hash password using bcrypt with automatic salt generation."""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def validate_username(username: str) -> str:
    """Validate username format (alphanumeric, underscores, hyphens, dots, 3-32 chars)."""
    username = (username or "").strip()
    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,32}$", username):
        raise ValueError("Username must be 3-32 characters and contain only letters, numbers, _, -, or .")
    return username

def register_user(username: str, password: str) -> Dict[str, Any]:
    """Register a new user with validated username and hashed password."""
    clean_username = validate_username(username)
    if db.get_user_by_username(clean_username):
        raise ValueError(f"Username '{clean_username}' is already taken.")
    hashed = hash_password(password)
    user = db.create_user(clean_username, hashed)
    return user

def login_user(username: str, password: str) -> Tuple[Dict[str, Any], str]:
    """Authenticate user with username and password, then generate session token."""
    clean_username = (username or "").strip()
    user_record = db.get_user_by_username(clean_username)
    if not user_record:
        raise ValueError("Invalid username or password.")
    if not verify_password(password, user_record["password_hash"]):
        raise ValueError("Invalid username or password.")

    token = db.create_auth_session(user_record["id"])
    user_info = {
        "id": user_record["id"],
        "username": user_record["username"],
        "created_at": user_record["created_at"]
    }
    return user_info, token

def logout_user(token: str) -> bool:
    """Invalidate session token."""
    return db.delete_auth_session(token)

def get_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Resolve authenticated user from session token."""
    return db.get_user_by_token(token)

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve user by ID."""
    return db.get_user_by_id(user_id)
