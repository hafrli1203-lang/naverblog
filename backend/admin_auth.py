"""
관리자 인증 — 환경변수 비밀번호 + HMAC-SHA256 토큰.

ADMIN_PASSWORD 환경변수 필수 (미설정 시 관리자 기능 비활성).
SECRET_KEY 환경변수 권장 (미설정 시 기본값 사용).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException, Request

ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY: str = os.getenv("SECRET_KEY", "naverblog-default-secret-change-me")


def verify_password(password: str) -> bool:
    """환경변수 비밀번호와 일치하는지 확인."""
    if not ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(password, ADMIN_PASSWORD)


def create_token() -> str:
    """24시간 유효 HMAC-SHA256 토큰 생성."""
    payload = {"exp": int(time.time()) + 86400, "role": "admin"}
    msg = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(msg).decode() + "." + sig


def verify_token(token: str) -> bool:
    """토큰 서명 + 만료 시간 검증."""
    if not token:
        return False
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        msg_b64, sig = parts
        msg = base64.urlsafe_b64decode(msg_b64 + "==")
        expected_sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False
        payload = json.loads(msg)
        if payload.get("exp", 0) < time.time():
            return False
        return True
    except Exception:
        return False


async def require_admin(request: Request) -> None:
    """FastAPI dependency — 관리자 인증 필수."""
    token = (
        request.cookies.get("admin_token")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="관리자 인증 필요")
