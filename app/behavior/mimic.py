"""Human behavioral mimicry: Bezier curves, micro-jitter, natural typing with typos, smooth scroll."""

from __future__ import annotations

import asyncio
import math
import random
from typing import Any

from patchright.async_api import Locator, Page

from app.config import get_settings


def _bezier_curve(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Cubic Bezier curve point calculation."""
    cx = 3 * (p1[0] - p0[0])
    bx = 3 * (p2[0] - p1[0]) - cx
    ax = p3[0] - p0[0] - cx - bx

    cy = 3 * (p1[1] - p0[1])
    by = 3 * (p2[1] - p1[1]) - cy
    ay = p3[1] - p0[1] - cy - by

    t2 = t * t
    t3 = t2 * t
    x = (ax * t3) + (bx * t2) + (cx * t) + p0[0]
    y = (ay * t3) + (by * t2) + (cy * t) + p0[1]
    return (x, y)


async def random_pause(
    mean: float | None = None, min_s: float = 1.0, max_s: float = 8.0
) -> None:
    """Asynchronously sleep using exponential distribution around mean."""
    settings = get_settings()
    target_mean = mean if mean is not None else settings.action_pause_mean
    # Exponential distribution with lower and upper bounds
    delay = random.expovariate(1.0 / max(target_mean, 0.5))
    clamped = max(min_s, min(max_s, delay))
    await asyncio.sleep(clamped)


async def delay_between_applies() -> float:
    """Enforce minimum delay between applications (at least 15s, randomized 15-30s)."""
    settings = get_settings()
    min_delay = max(15.0, float(settings.min_delay_between_applies_sec))
    max_delay = max(min_delay + 5.0, float(settings.max_delay_between_applies_sec))

    # Randomized delay with exponential distribution
    span = max_delay - min_delay
    raw = random.expovariate(1.5 / span) if span > 0 else 0
    actual_delay = min_delay + min(span, raw)
    await asyncio.sleep(actual_delay)
    return actual_delay


async def human_move_mouse(
    page: Page, target_x: float, target_y: float, steps: int = 25
) -> None:
    """Move cursor along a natural curved Bezier path with micro-jitter."""
    # Approximate current cursor position or start near center
    start_x = getattr(page, "_last_cursor_x", 200.0)
    start_y = getattr(page, "_last_cursor_y", 400.0)

    # Control points for Bezier curve with randomized deviation
    deviation_x = (target_x - start_x) * 0.2 + random.uniform(-40, 40)
    deviation_y = (target_y - start_y) * 0.2 + random.uniform(-40, 40)

    p0 = (start_x, start_y)
    p1 = (start_x + deviation_x, start_y + deviation_y)
    p2 = (target_x - deviation_x * 0.5, target_y - deviation_y * 0.5)
    p3 = (target_x, target_y)

    for i in range(1, steps + 1):
        t = i / steps
        bx, by = _bezier_curve(p0, p1, p2, p3, t)
        # Micro-jitter
        jitter_x = random.gauss(0, 0.5)
        jitter_y = random.gauss(0, 0.5)
        curr_x = bx + jitter_x
        curr_y = by + jitter_y
        await page.mouse.move(curr_x, curr_y)
        # Random step timing between 4ms and 14ms
        await asyncio.sleep(random.uniform(0.004, 0.014))

    setattr(page, "_last_cursor_x", target_x)
    setattr(page, "_last_cursor_y", target_y)


async def human_click(
    page: Page, target: str | Locator, miss_click_rate: float | None = None
) -> None:
    """Click an element using human trajectory, pre-click hesitation, and optional correction."""
    settings = get_settings()
    rate = miss_click_rate if miss_click_rate is not None else settings.miss_click_rate

    locator = page.locator(target) if isinstance(target, str) else target
    await locator.scroll_into_view_if_needed()
    box = await locator.bounding_box()
    if not box:
        # Fallback to direct click if bounding box unavailable
        await locator.click()
        return

    center_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    center_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

    # 5% probability of a near-miss click with hesitation and correction
    if random.random() < rate:
        miss_x = center_x + random.choice([-1, 1]) * random.uniform(15, 30)
        miss_y = center_y + random.choice([-1, 1]) * random.uniform(15, 30)
        await human_move_mouse(page, miss_x, miss_y, steps=18)
        await asyncio.sleep(random.uniform(0.08, 0.18))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.04, 0.09))
        await page.mouse.up()
        # Pause as if realizing the miss
        await asyncio.sleep(random.uniform(0.15, 0.35))

    # Move to true target
    await human_move_mouse(page, center_x, center_y, steps=random.randint(18, 30))

    # Pre-tap hesitation
    await asyncio.sleep(random.uniform(0.06, 0.22))
    try:
        await locator.click(timeout=3000)
    except Exception:
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await page.mouse.up()
    # Post-click pause
    await asyncio.sleep(random.uniform(0.1, 0.3))


async def human_typing(
    page: Page, target: str | Locator, text: str, typo_rate: float | None = None
) -> None:
    """Type text into an element with Gaussian delays, typos, and correction backspaces.
    For long texts (e.g., cover letters > 80 chars), simulates realistic human workflow:
    types initial greeting/words, pauses naturally, and inserts remainder (paste simulation)
    to prevent unnatural 3-minute freezes while correctly firing all React synthetic events."""
    settings = get_settings()
    t_rate = typo_rate if typo_rate is not None else settings.typo_rate
    mean_ms = settings.typing_mean_ms
    std_ms = settings.typing_std_ms

    locator = page.locator(target) if isinstance(target, str) else target
    await human_click(page, locator)

    if len(text) > 80:
        # Realistic human workflow: type opening 10-18 characters naturally
        intro_len = min(random.randint(10, 18), len(text))
        intro_part = text[:intro_len]
        remainder = text[intro_len:]

        for char in intro_part:
            await page.keyboard.type(char)
            delay_ms = random.gauss(mean_ms, std_ms)
            clamped_ms = max(25.0, min(250.0, delay_ms))
            await asyncio.sleep(clamped_ms / 1000.0)

        # Brief pause as if switching tabs or pasting draft
        await asyncio.sleep(random.uniform(0.4, 0.8))

        # Insert remainder directly (fires native beforeinput, input, change in React DOM)
        if remainder:
            await page.keyboard.insert_text(remainder)

        # Post-paste inspection pause
        await asyncio.sleep(random.uniform(0.5, 1.1))
        return

    russian_nearby_keys: dict[str, str] = {
        "а": "прв", "б": "ьюд", "в": "ыас", "г": "неш", "д": "лоб",
        "е": "кун", "ж": "длэ", "з": "хщж", "и": "мтп", "к": "уег",
        "л": "одб", "м": "си", "н": "егг", "о": "рлщ", "п": "ари",
        "р": "поо", "с": "мвы", "т": "иьн", "у": "йке", "ф": "яы",
        "х": "зъ", "ц": "йуы", "ч": "ся", "ш": "гщ", "щ": "шз",
        "ъ": "хэ", "ы": "вфа", "ь": "тиб", "э": "жъ", "ю": "б.",
        "я": "фч",
    }

    for char in text:
        # Check typo chance on alphabetic chars
        if random.random() < t_rate and char.lower() in russian_nearby_keys:
            wrong_char = random.choice(russian_nearby_keys[char.lower()])
            await page.keyboard.type(wrong_char)
            # Reaction delay noticing typo
            await asyncio.sleep(random.uniform(0.12, 0.28))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.08, 0.20))

        await page.keyboard.type(char)

        # Typing delay drawn from Normal distribution N(mean_ms, std_ms)
        delay_ms = random.gauss(mean_ms, std_ms)
        clamped_ms = max(30.0, min(450.0, delay_ms))
        await asyncio.sleep(clamped_ms / 1000.0)


async def human_scroll(
    page: Page, total_pixels: int = 500, direction: int = 1
) -> None:
    """Smooth scroll with natural velocity decay, micro-pauses, and 10% rollback chance."""
    settings = get_settings()
    scrolled = 0
    step_size = random.randint(40, 90)

    while scrolled < total_pixels:
        current_step = min(step_size, total_pixels - scrolled) * direction
        await page.mouse.wheel(0, current_step)
        scrolled += abs(current_step)

        # Micro-pause between wheel chunks
        await asyncio.sleep(random.uniform(0.03, 0.08))

        # Occasional pause reading
        if random.random() < 0.25:
            await asyncio.sleep(
                random.uniform(settings.scroll_pause_min, settings.scroll_pause_max)
            )

        # ~10% chance of micro-rollback upwards
        if random.random() < 0.10:
            rollback = random.randint(30, 80)
            await page.mouse.wheel(0, -rollback * direction)
            await asyncio.sleep(random.uniform(0.2, 0.5))

    await asyncio.sleep(random.uniform(0.2, 0.6))


async def imitate_reading(page: Page, description_locator: Locator | None = None) -> None:
    """Imitate candidate reading through vacancy description before applying."""
    if description_locator:
        try:
            await description_locator.scroll_into_view_if_needed()
        except Exception:
            pass

    # Read description through 2-4 scrolls and reading pauses
    scroll_rounds = random.randint(2, 4)
    for _ in range(scroll_rounds):
        await human_scroll(page, total_pixels=random.randint(250, 450))
        # Reading pause
        await asyncio.sleep(random.uniform(1.2, 3.2))
