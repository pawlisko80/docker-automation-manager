"""
dam/web/auth.py

Simple HTTP Basic Auth with bcrypt-hashed passwords stored in settings.yaml.

Password setup:
  dam --web-passwd        # interactive: prompt for username/password, hash and save
  dam --web-passwd --user admin --password mypassword  # non-interactive

settings.yaml format:
  web:
    auth:
      - username: admin
        password_hash: $2b$12$...   # bcrypt hash

If no auth section is configured, all requests are allowed (trust network mode).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# Try bcrypt — fall back to sha256 if not available (QNAP minimal Python)
try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    # Test it actually works
    _pwd_context.hash("test"[:72])
    _USE_BCRYPT = True
except Exception:
    _USE_BCRYPT = False


security = HTTPBasic(auto_error=False)


# ------------------------------------------------------------
# Password hashing
# ------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password for storage in settings.yaml."""
    if _USE_BCRYPT:
        return _pwd_context.hash(password)
    # Fallback: sha256 with a random salt prefix
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"sha256:{salt}:{h}"


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a stored hash."""
    if hashed.startswith("sha256:"):
        _, salt, h = hashed.split(":", 2)
        return secrets.compare_digest(
            hashlib.sha256(f"{salt}{plain}".encode()).hexdigest(), h
        )
    if _USE_BCRYPT:
        try:
            return _pwd_context.verify(plain, hashed)
        except Exception:
            return False
    return False


# ------------------------------------------------------------
# Auth dependency factory
# ------------------------------------------------------------

def make_auth_dependency(users: list[dict]):
    """
    Returns a FastAPI dependency that validates HTTP Basic Auth.
    If users list is empty, auth is disabled (trust network mode).

    Args:
        users: list of {"username": str, "password_hash": str} dicts
               from settings.yaml web.auth section
    """

    if not users:
        # No auth configured — allow all
        async def no_auth():
            return "anonymous"
        return no_auth

    user_map = {u["username"]: u["password_hash"] for u in users if "username" in u}

    async def check_auth(
        credentials: Optional[HTTPBasicCredentials] = Depends(security),
    ) -> str:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic realm='DAM'"},
            )

        stored_hash = user_map.get(credentials.username)
        if not stored_hash or not verify_password(credentials.password, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic realm='DAM'"},
            )
        return credentials.username

    return check_auth
