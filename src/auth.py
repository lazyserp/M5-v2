"""
auth.py — M5 API Key Authentication

How it works (plain English):
- API keys look like:  m5_live_abc123...
- When a key is CREATED we hash it with sha256 and store only the hash in keys.json.
  The real key is shown to the user once and never stored anywhere.
- When a request arrives we hash the submitted key and compare hashes.
  So even if someone reads keys.json they can't recover the original key.
- verify_api_key  — used on /api/context and /mcp  (any valid key)
- verify_admin_key — used on /api/index/* and /api/admin/* (only M5_ADMIN_KEY)
"""

import os
import json
import secrets
import hashlib
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, Request, status
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Storage location ──────────────────────────────────────────────────────────
_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage"))
os.makedirs(_STORAGE_DIR, exist_ok=True)
_KEYS_FILE = os.path.join(_STORAGE_DIR, "keys.json")
_lock = threading.Lock()


def _get_admin_key() -> str:
    """
    Reads M5_ADMIN_KEY from environment at call time (not module-load time).
    This allows tests to set os.environ before calling auth functions,
    and allows the admin key to be updated without restarting the server.
    """
    return os.getenv("M5_ADMIN_KEY", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_key(raw_key: str) -> str:
    """SHA-256 hash of the raw key. This is what we store."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _load_keys() -> Dict[str, Any]:
    """Read keys.json from disk. Returns empty dict if file doesn't exist."""
    if not os.path.exists(_KEYS_FILE):
        return {}
    try:
        with open(_KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_keys(keys: Dict[str, Any]) -> None:
    """Write keys dict to keys.json atomically."""
    tmp = _KEYS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)
    os.replace(tmp, _KEYS_FILE)


# ── Public API ────────────────────────────────────────────────────────────────

def create_api_key(
    caller_name: str,
    org_id: str = "default_org",
    scopes: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Generates a new API key, stores its hash, and returns the raw key ONCE.
    The raw key is never stored — if lost, create a new one.
    """
    if scopes is None:
        scopes = ["read", "context"]

    raw_key = "m5_live_" + secrets.token_hex(24)   # 48-char random suffix
    key_hash = _hash_key(raw_key)
    key_id = "kid_" + secrets.token_hex(6)

    record = {
        "key_id": key_id,
        "key_hash": key_hash,
        "caller_name": caller_name,
        "org_id": org_id,
        "scopes": scopes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }

    with _lock:
        keys = _load_keys()
        keys[key_id] = record
        _save_keys(keys)

    return {
        "key_id": key_id,
        "key": raw_key,          # shown ONCE — user must save this
        "api_key": raw_key,      # alias for client compatibility
        "caller_name": caller_name,
        "org_id": org_id,
        "scopes": scopes,
        "created_at": record["created_at"],
        "message": "Save this key — it will not be shown again.",
    }


def list_api_keys() -> list:
    """Returns all key records (without hashes or raw keys)."""
    with _lock:
        keys = _load_keys()
    return [
        {
            "key_id": v["key_id"],
            "caller_name": v["caller_name"],
            "org_id": v["org_id"],
            "scopes": v["scopes"],
            "created_at": v["created_at"],
            "is_active": v["is_active"],
        }
        for v in keys.values()
    ]


def revoke_api_key(key_id: str) -> bool:
    """Soft-deletes a key by marking it inactive. Returns True if found."""
    with _lock:
        keys = _load_keys()
        if key_id not in keys:
            return False
        keys[key_id]["is_active"] = False
        _save_keys(keys)
    return True


def _lookup_key(raw_key: str) -> Optional[Dict[str, Any]]:
    """Returns the key record if the raw key matches any active stored hash."""
    submitted_hash = _hash_key(raw_key)
    with _lock:
        keys = _load_keys()
    for record in keys.values():
        if record.get("is_active") and record.get("key_hash") == submitted_hash:
            return record
    return None


def _extract_bearer(request: Request) -> Optional[str]:
    """Pulls the raw key out of the Authorization: Bearer <key> header."""
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


# ── FastAPI Dependencies ──────────────────────────────────────────────────────

def verify_api_key(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency for /api/context and /mcp.
    Accepts any active API key OR the admin key.
    Raises HTTP 401 if no key is supplied, HTTP 403 if key is invalid.
    """
    admin_key = _get_admin_key()
    raw_key = _extract_bearer(request)

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide: Authorization: Bearer <your-m5-api-key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Admin key is always valid
    if admin_key and raw_key == admin_key:
        return {"caller_name": "admin", "org_id": "admin", "scopes": ["*"]}

    # Check stored API keys
    record = _lookup_key(raw_key)
    if record:
        return record

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or revoked API key.",
    )


def verify_admin_key(request: Request) -> None:
    """
    FastAPI dependency for /api/admin/* and /api/index/*.
    Only the M5_ADMIN_KEY from .env is accepted — not regular API keys.
    """
    admin_key = _get_admin_key()
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: M5_ADMIN_KEY is not set.",
        )

    raw_key = _extract_bearer(request)
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required. Provide: Authorization: Bearer <M5_ADMIN_KEY>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if raw_key != admin_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key.",
        )
