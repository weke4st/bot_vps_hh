"""Tests for SaaS admin panel, registration request approval workflow, and security hardening."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.database import get_session_dep
from app.db.models import Base
from app.main import create_app


@pytest.fixture
async def saas_client():
    """Create isolated in-memory DB and AsyncClient for SaaS auth & admin tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    app = create_app()

    async def override_get_session():
        async with session_factory() as sess:
            yield sess

    app.dependency_overrides[get_session_dep] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_jwt_secret_not_default() -> None:
    """Verify insecure hardcoded placeholder JWT secret is never used."""
    settings = get_settings()
    assert settings.jwt_secret != "hh-bot-super-secret-jwt-key-change-in-production"
    assert len(settings.jwt_secret) >= 32


@pytest.mark.asyncio
async def test_registration_approval_and_admin_workflow(saas_client) -> None:
    """Test first admin bootstrap, pending approval queue, manual creation, blocking, and closed mode."""
    client, _ = saas_client

    # Anonymous access to logs must be rejected
    assert (await client.get("/api/logs")).status_code == 401

    # Initially DB is empty -> first_admin mode
    cfg1 = await client.get("/api/auth/config")
    assert cfg1.status_code == 200
    assert cfg1.json()["registration_mode"] == "first_admin"

    # First user becomes admin immediately
    r1 = await client.post(
        "/api/auth/register",
        json={"email": "admin@example.com", "password": "password123", "full_name": "Owner"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "approved"
    assert r1.json()["user"]["is_admin"] is True
    admin_headers = {"Authorization": f"Bearer {r1.json()['access_token']}"}

    # Mode switches to request-approval
    cfg2 = await client.get("/api/auth/config")
    assert cfg2.json()["registration_mode"] == "request"

    # Second user submits request -> pending, no token issued
    r2 = await client.post(
        "/api/auth/register",
        json={
            "email": "guest@example.com",
            "password": "password123",
            "full_name": "Guest",
            "note": "@guest_tg",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "pending"
    assert r2.json()["access_token"] is None

    # Pending user cannot log in yet
    assert (
        await client.post(
            "/api/auth/login", json={"email": "guest@example.com", "password": "password123"}
        )
    ).status_code == 403

    # Admin sees pending request and approves it
    users_resp = await client.get("/api/admin/users", headers=admin_headers)
    assert users_resp.status_code == 200
    assert users_resp.json()["summary"]["pending_count"] == 1
    guest_id = next(u["id"] for u in users_resp.json()["users"] if u["email"] == "guest@example.com")

    assert (
        await client.post(f"/api/admin/users/{guest_id}/approve", headers=admin_headers)
    ).status_code == 200

    # Guest can now log in, but cannot access admin API
    guest_login = await client.post(
        "/api/auth/login", json={"email": "guest@example.com", "password": "password123"}
    )
    assert guest_login.status_code == 200
    guest_headers = {"Authorization": f"Bearer {guest_login.json()['access_token']}"}
    assert (await client.get("/api/admin/users", headers=guest_headers)).status_code == 403

    # Admin blocks guest -> active token rejected immediately
    assert (
        await client.post(f"/api/admin/users/{guest_id}/toggle-active", headers=admin_headers)
    ).status_code == 200
    assert (await client.get("/api/auth/me", headers=guest_headers)).status_code == 403

    # Admin creates a user directly
    manual_resp = await client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "direct@example.com",
            "password": "password123",
            "full_name": "Direct",
            "is_admin": False,
        },
    )
    assert manual_resp.status_code == 200
    assert manual_resp.json()["approval_status"] == "approved"

    # Admin switches off public requests -> public signup forbidden
    assert (
        await client.put(
            "/api/admin/settings",
            headers=admin_headers,
            json={"allow_registration_requests": False},
        )
    ).status_code == 200
    assert (await client.get("/api/auth/config")).json()["registration_mode"] == "closed"
    assert (
        await client.post(
            "/api/auth/register",
            json={"email": "blocked@example.com", "password": "password123", "full_name": "X"},
        )
    ).status_code == 403
