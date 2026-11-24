"""Cover letter generator using GigaChat API with automatic fallback to DeepSeek."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories import create_llm_call, get_setting

logger = logging.getLogger(__name__)

COVER_LETTER_SYSTEM_PROMPT = """Ты — опытный карьерный консультант и технический специалист.
Твоя задача — написать убедительное, персонализированное сопроводительное письмо на русском языке для отклика на вакансию.

Правила:
1. Выдели 3-5 ключевых технических требований из текста вакансии.
2. Сопоставь их с реальным опытом кандидата из резюме.
3. Обязательно упомяни название компании и конкретные технологии, с которыми кандидат работал.
4. Тон: профессиональный, уважительный, уверенный, без шаблонных фраз и "воды" (без выражений вроде "Я динамичный командный игрок").
5. Объем: 150-250 слов.
6. Выводи ТОЛЬКО текст письма, без вводных фраз вроде "Вот ваше письмо:" и без кавычек.
"""


class GigaChatTokenManager:
    """Manages 30-minute OAuth tokens for Sber GigaChat API (supports per-user key)."""

    def __init__(self, auth_key: str | None = None, scope: str | None = None) -> None:
        self.settings = get_settings()
        self.custom_auth_key = auth_key
        self.custom_scope = scope or self.settings.gigachat_scope
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    async def get_token(self) -> str:
        """Return valid access token, refreshing via OAuth endpoint if needed."""
        now = time.time()
        # Refresh 60 seconds before expiration
        if self._access_token and now < (self._expires_at - 60):
            return self._access_token

        auth_key = self.custom_auth_key or self.settings.gigachat_auth_key.get_secret_value()
        if not auth_key:
            raise ValueError("GigaChat auth key is empty")

        headers = {
            "Authorization": f"Basic {auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"scope": self.custom_scope}

        logger.info("Requesting fresh GigaChat OAuth token...")
        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            resp = await client.post(
                self.settings.gigachat_oauth_url, headers=headers, data=data
            )
            resp.raise_for_status()
            res_json = resp.json()

        self._access_token = res_json["access_token"]
        # expires_at is given in milliseconds Unix timestamp
        exp_ms = res_json.get("expires_at", (now + 1800) * 1000)
        self._expires_at = exp_ms / 1000.0
        logger.info("GigaChat OAuth token obtained successfully (expires in ~30 min)")
        return self._access_token


class CoverLetterGenerator:
    """Generates customized cover letters using GigaChat with DeepSeek fallback."""

    def __init__(self, auth_key: str | None = None, scope: str | None = None) -> None:
        self.settings = get_settings()
        self.gigachat_tokens = GigaChatTokenManager(auth_key=auth_key, scope=scope)

    async def _generate_gigachat(
        self, prompt: str
    ) -> tuple[str, int, int, int]:
        """Generate via GigaChat using OpenAI SDK compatibility. Returns (text, prompt_tokens, comp_tokens, latency_ms)."""
        token = await self.gigachat_tokens.get_token()

        client = AsyncOpenAI(
            base_url=self.settings.gigachat_base_url,
            api_key=token,
            http_client=httpx.AsyncClient(verify=False, timeout=35.0),
        )

        start_t = time.perf_counter()
        response = await client.chat.completions.create(
            model=self.settings.gigachat_model,
            messages=[
                {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
        )
        latency_ms = int((time.perf_counter() - start_t) * 1000)

        choice = response.choices[0]
        text = choice.message.content or ""
        p_tok = response.usage.prompt_tokens if response.usage else 0
        c_tok = response.usage.completion_tokens if response.usage else 0
        return text.strip(), p_tok, c_tok, latency_ms

    async def _generate_deepseek(
        self, prompt: str
    ) -> tuple[str, int, int, int]:
        """Generate via DeepSeek API. Returns (text, prompt_tokens, comp_tokens, latency_ms)."""
        api_key = self.settings.deepseek_api_key.get_secret_value()
        if not api_key:
            raise ValueError("DeepSeek API key is not configured")

        client = AsyncOpenAI(
            base_url=self.settings.deepseek_base_url,
            api_key=api_key,
            timeout=35.0,
        )

        start_t = time.perf_counter()
        response = await client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=[
                {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
        )
        latency_ms = int((time.perf_counter() - start_t) * 1000)

        choice = response.choices[0]
        text = choice.message.content or ""
        p_tok = response.usage.prompt_tokens if response.usage else 0
        c_tok = response.usage.completion_tokens if response.usage else 0
        return text.strip(), p_tok, c_tok, latency_ms

    async def generate(
        self,
        *,
        vacancy_title: str,
        company: str,
        description: str,
        resume_text: str,
        application_id: int | None = None,
        session: AsyncSession | None = None,
    ) -> str:
        """Generate cover letter with automatic provider fallback and DB audit logging."""
        prompt = (
            f"Вакансия: {vacancy_title}\n"
            f"Компания: {company}\n\n"
            f"Описание вакансии:\n{description[:3500]}\n\n"
            f"Резюме кандидата:\n{resume_text[:3500]}\n"
        )

        provider_order = (
            ["gigachat", "deepseek"]
            if self.settings.llm_provider == "gigachat"
            else ["deepseek", "gigachat"]
        )

        last_error: Exception | None = None

        for provider in provider_order:
            try:
                logger.info("Attempting cover letter generation with %s...", provider)
                if provider == "gigachat":
                    text, p_tok, c_tok, latency = await self._generate_gigachat(prompt)
                    model_name = self.settings.gigachat_model
                else:
                    text, p_tok, c_tok, latency = await self._generate_deepseek(prompt)
                    model_name = self.settings.deepseek_model

                # Validate minimum length requirement
                if len(text) < 100:
                    raise ValueError(
                        f"Generated letter is too short ({len(text)} chars), expected >= 100"
                    )

                logger.info(
                    "Cover letter successfully generated via %s (%d chars, %d ms)",
                    provider,
                    len(text),
                    latency,
                )

                # Log LLM call to DB
                if session:
                    await create_llm_call(
                        session,
                        application_id=application_id,
                        provider=provider,
                        model=model_name,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        latency_ms=latency,
                    )
                    await session.commit()

                return text

            except Exception as exc:
                logger.warning(
                    "Provider %s failed to generate letter: %s", provider, exc
                )
                last_error = exc

        raise RuntimeError(
            f"All LLM providers failed to generate cover letter. Last error: {last_error}"
        )
