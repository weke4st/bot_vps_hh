"""Unit and integration tests for FastAPI REST routes and WebSocket endpoint."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_session_dep
from app.db.models import (
    Application,
    ApplicationStatus,
    Base,
    CaptchaAttempt,
    DailyStats,
    LLMCall,
    Vacancy,
    VacancyStatus,
)
from app.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def app_client():
    """Create in-memory database and test client."""
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    await engine.dispose()


# ---------------------------------------------------------------------------
# Health & General
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check(app_client) -> None:
    client, _ = app_client
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_empty(app_client) -> None:
    client, _ = app_client
    resp = await client.get("/api/stats?period=7d")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_applications"] == 0
    assert data["response_rate_pct"] == 0.0
    assert isinstance(data["timeline"], list)
    assert isinstance(data["status_distribution"], dict)


@pytest.mark.asyncio
async def test_get_stats_with_data(app_client) -> None:
    client, session_factory = app_client

    # Populate some test data
    async with session_factory() as session:
        today = date.today()
        session.add(
            DailyStats(
                date=today,
                applications_count=10,
                responses_count=2,
                interviews_count=1,
            )
        )
        v = Vacancy(
            hh_id="v1",
            title="Backend Dev",
            company="Yandex",
            description="Good job",
            url="https://hh.ru/1",
        )
        session.add(v)
        await session.flush()

        app = Application(
            vacancy_id=v.id,
            status=ApplicationStatus.sent,
            sent_at=datetime.now(timezone.utc),
        )
        session.add(app)
        await session.commit()

    resp = await client.get("/api/stats?period=7d")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_applications"] == 10
    assert data["total_responses"] == 2
    assert data["total_interviews"] == 1
    assert data["response_rate_pct"] == 20.0
    assert len(data["timeline"]) >= 1


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_applications_crud_and_retry(app_client) -> None:
    client, session_factory = app_client

    async with session_factory() as session:
        v = Vacancy(
            hh_id="test_vac",
            title="Senior Python",
            company="VK",
            description="Work with us",
            url="https://hh.ru/v2",
            salary="300 000 руб.",
        )
        session.add(v)
        await session.flush()

        app = Application(
            vacancy_id=v.id,
            status=ApplicationStatus.manual,
            cover_letter="Hello there, I am a great fit!",
        )
        session.add(app)
        await session.flush()
        app_id = app.id

        # Add a captcha attempt and LLM call
        session.add(
            CaptchaAttempt(
                application_id=app_id,
                image_path="test.png",
                model_answer="1234",
                correct=True,
            )
        )
        session.add(
            LLMCall(
                application_id=app_id,
                provider="gigachat",
                model="GigaChat",
                prompt_tokens=50,
                completion_tokens=25,
                latency_ms=200,
            )
        )
        await session.commit()

    # List applications
    list_resp = await client.get("/api/applications?page=1&limit=10")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["status"] == "manual"
    assert list_data["items"][0]["vacancy"]["company"] == "VK"

    # Detail application
    detail_resp = await client.get(f"/api/applications/{app_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["cover_letter"] == "Hello there, I am a great fit!"
    assert len(detail_data["captcha_attempts"]) == 1
    assert len(detail_data["llm_calls"]) == 1

    # Retry application
    retry_resp = await client.post(f"/api/applications/{app_id}/retry")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["success"] is True

    # Verify status changed to pending
    recheck_resp = await client.get(f"/api/applications/{app_id}")
    assert recheck_resp.json()["status"] == "pending"


# ---------------------------------------------------------------------------
# Settings & Resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_endpoints(app_client) -> None:
    client, _ = app_client

    get_resp = await client.get("/api/settings")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "max_applications_per_hour" in data
    assert "llm_provider" in data

    # Update settings
    put_resp = await client.put(
        "/api/settings",
        json={
            "max_applications_per_hour": 35,
            "search_query": "Golang developer",
        },
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["max_applications_per_hour"] == 35
    assert updated["search_query"] == "Golang developer"


@pytest.mark.asyncio
async def test_resume_endpoints(app_client) -> None:
    client, _ = app_client

    # Get empty resume
    get_resp = await client.get("/api/resume")
    assert get_resp.status_code == 200
    assert get_resp.json()["text"] == ""

    # Update resume
    put_resp = await client.put(
        "/api/resume",
        json={"text": "Experienced Senior Python Engineer with 6+ years..."},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["success"] is True

    # Verify resume updated
    get2_resp = await client.get("/api/resume")
    assert get2_resp.status_code == 200
    assert "Experienced Senior Python" in get2_resp.json()["text"]
    assert get2_resp.json()["updated_at"] is not None


# ---------------------------------------------------------------------------
# Bot Control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bot_control_endpoints(app_client) -> None:
    client, _ = app_client

    status_resp = await client.get("/api/bot/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "status" in status_data
    assert "limits" in status_data

    # Start bot
    start_resp = await client.post("/api/bot/start")
    assert start_resp.status_code == 200

    status2_resp = await client.get("/api/bot/status")
    assert status2_resp.json()["is_running"] is True

    # Stop bot
    stop_resp = await client.post("/api/bot/stop")
    assert stop_resp.status_code == 200

    status3_resp = await client.get("/api/bot/status")
    assert status3_resp.json()["status"] == "stopped"


# ---------------------------------------------------------------------------
# Logs & WebSocket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logs_endpoint(app_client) -> None:
    client, _ = app_client

    resp = await client.get("/api/logs?limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "total" in data
    assert isinstance(data["logs"], list)


def test_websocket_stream() -> None:
    """Test live websocket stream sends status and snapshot on connect."""
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws") as ws:
            status_msg = ws.receive_json()
            assert status_msg["type"] == "bot_status"
            assert "status" in status_msg["data"]

            logs_msg = ws.receive_json()
            assert logs_msg["type"] == "logs_snapshot"
            assert isinstance(logs_msg["data"], list)

            ws.send_text("ping")
            pong = ws.receive_text()
            assert pong == "pong"

