import asyncio
import pytest
from datetime import datetime
from src.clients.xai_client import XAIClient
from src.utils.database import DatabaseManager
from src.config.settings import settings


@pytest.mark.asyncio
async def test_xai_client_respects_db_daily_budget(tmp_path):
    db_path = str(tmp_path / "test_db.db")
    db = DatabaseManager(db_path=db_path)
    await db.initialize()

    # Insert a daily cost above the configured budget
    today = datetime.now().strftime('%Y-%m-%d')
    import aiosqlite
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("INSERT OR REPLACE INTO daily_cost_tracking (date, total_ai_cost, analysis_count, decision_count) VALUES (?, ?, 1, 0)", (today, settings.trading.daily_ai_budget * 10))
        await conn.commit()

    xai = XAIClient(db_manager=db)

    can_proceed = await xai._check_daily_limits()
    assert can_proceed is False, "XAI client should refuse requests when DB shows budget exceeded"

    await xai.close()


@pytest.mark.asyncio
async def test_beastmode_checks_xai_limits(tmp_path):
    from beast_mode_bot import BeastModeBot

    db_path = str(tmp_path / "test_db2.db")
    db = DatabaseManager(db_path=db_path)
    await db.initialize()

    # Add daily cost exceeding budget
    today = datetime.now().strftime('%Y-%m-%d')
    import aiosqlite
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("INSERT OR REPLACE INTO daily_cost_tracking (date, total_ai_cost, analysis_count, decision_count) VALUES (?, ?, 1, 0)", (today, settings.trading.daily_ai_budget * 5))
        await conn.commit()

    xai = XAIClient(db_manager=db)
    bot = BeastModeBot(live_mode=False, dashboard_mode=False)

    can_continue = await bot._check_daily_ai_limits(xai)
    assert can_continue is False, "BeastModeBot should pause trading when XAI client reports limits reached"

    await xai.close()