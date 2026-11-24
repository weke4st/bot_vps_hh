"""Simple Bearer token authentication dependency for local/single-user API."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

security_bearer = HTTPBearer(auto_error=False)


def verify_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)] = None,
    token_query: Annotated[str | None, Query(alias="token")] = None,
) -> bool:
    """Verify incoming Bearer token from Authorization header or ?token= query.

    Raises:
        HTTPException(401): If token is missing or invalid.
    """
    settings = get_settings()
    expected_token = settings.api_token.get_secret_value()

    # If default token is "changeme" and no token is passed, allow dev access
    # but still validate if expected token is customized
    provided_token: str | None = None

    if credentials and credentials.credentials:
        provided_token = credentials.credentials
    elif token_query:
        provided_token = token_query

    if not provided_token:
        # If token is still default "changeme" / unconfigured, allow seamless local developer usage
        if expected_token.startswith("changeme") or not expected_token:
            return True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token or token parameter",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison
    if not secrets.compare_digest(provided_token, expected_token):
        if not expected_token.startswith("changeme"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return True


def verify_ws_token(token: str | None) -> bool:
    """Verify WebSocket query token without raising HTTP exceptions."""
    settings = get_settings()
    expected = settings.api_token.get_secret_value()

    if expected.startswith("changeme") or not expected:
        return True
    if not token:
        return False
    return secrets.compare_digest(token, expected)
