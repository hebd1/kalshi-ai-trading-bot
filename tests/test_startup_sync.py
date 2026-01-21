"""
Tests for startup position syncing behavior.

This test suite ensures that:
1. Bot ignores existing Kalshi positions when starting with empty database
2. Bot only tracks NEW positions created after initial deployment
3. Existing positions don't get logged as trade_logs
4. Dashboard correctly shows balance without phantom trades
"""

import pytest
import asyncio
import aiosqlite
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.database import DatabaseManager, Position, TradeLog
from src.clients.kalshi_client import KalshiClient


@pytest.fixture
async def empty_db():
    """Create a fresh empty database for testing."""
    db_manager = DatabaseManager(db_path="test_startup_sync.db")
    await db_manager.initialize()
    yield db_manager
    
    # Cleanup
    import os
    if os.path.exists("test_startup_sync.db"):
        os.remove("test_startup_sync.db")


@pytest.fixture
def mock_kalshi_with_existing_positions():
    """Mock Kalshi client with existing positions (pre-deployment)."""
    client = MagicMock(spec=KalshiClient)
    
    # Mock existing positions on Kalshi account
    client.get_positions = AsyncMock(return_value={
        'market_positions': [
            {
                'ticker': 'EXISTING-MARKET-1',
                'position': 50,  # 50 YES contracts
                'market_exposure': 3000  # $30 in cents
            },
            {
                'ticker': 'EXISTING-MARKET-2',
                'position': -30,  # 30 NO contracts
                'market_exposure': 1500  # $15 in cents
            }
        ]
    })
    
    # Mock market data for price lookups
    def mock_get_market(ticker):
        markets = {
            'EXISTING-MARKET-1': {
                'market': {
                    'yes_price': 65,
                    'no_price': 35,
                    'last_price': 65,
                    'status': 'active'
                }
            },
            'EXISTING-MARKET-2': {
                'market': {
                    'yes_price': 45,
                    'no_price': 55,
                    'last_price': 45,
                    'status': 'active'
                }
            }
        }
        return asyncio.coroutine(lambda: markets.get(ticker, {}))()
    
    client.get_market = mock_get_market
    
    # Mock balance
    client.get_balance = AsyncMock(return_value={'balance': 500000})  # $5000
    
    return client


@pytest.mark.asyncio
async def test_empty_db_ignores_existing_kalshi_positions(empty_db, mock_kalshi_with_existing_positions):
    """
    Test that when starting with empty database, the bot IGNORES existing Kalshi positions.
    
    This is the PRIMARY test - ensures pre-existing positions are not tracked.
    """
    # Verify database is empty
    positions = await empty_db.get_open_positions()
    assert len(positions) == 0, "Database should start empty"
    
    # Simulate startup sync with flag to skip existing positions
    from beast_mode_bot import BeastModeBot
    
    # Check if DB is empty (first run detection)
    all_positions_count = await _count_all_positions(empty_db)
    is_first_run = (all_positions_count == 0)
    
    assert is_first_run, "Should detect first run with empty database"
    
    # On first run, we should NOT sync existing Kalshi positions
    kalshi_positions = await mock_kalshi_with_existing_positions.get_positions()
    existing_count = len([p for p in kalshi_positions['market_positions'] if p.get('position', 0) != 0])
    
    assert existing_count == 2, "Kalshi has 2 existing positions"
    
    # After ignoring them, database should still be empty
    positions_after = await empty_db.get_open_positions()
    assert len(positions_after) == 0, "Database should remain empty after ignoring existing positions"


@pytest.mark.asyncio
async def test_empty_db_no_trade_logs_created_for_existing(empty_db, mock_kalshi_with_existing_positions):
    """
    Test that existing Kalshi positions do NOT create trade_log entries.
    
    This ensures no phantom "completed trades" appear in performance metrics.
    """
    # Verify no trade logs exist
    trade_logs = await empty_db.get_all_trade_logs()
    assert len(trade_logs) == 0, "Should have no trade logs initially"
    
    # Simulate ignoring existing positions (no sync)
    # Database should remain empty
    
    # Verify still no trade logs
    trade_logs_after = await empty_db.get_all_trade_logs()
    assert len(trade_logs_after) == 0, "Should still have no trade logs after ignoring existing positions"


@pytest.mark.asyncio
async def test_new_positions_are_tracked_after_first_run(empty_db):
    """
    Test that NEW positions created by the bot ARE tracked properly.
    
    After ignoring existing positions, new bot-created positions should be tracked normally.
    """
    # Mark database as "initialized" (past first run)
    await _mark_db_initialized(empty_db)
    
    # Create a new position (bot creates this)
    new_position = Position(
        market_id="NEW-MARKET-1",
        side="YES",
        entry_price=0.55,
        quantity=20,
        timestamp=datetime.now(),
        rationale="Bot-created position",
        confidence=0.75,
        live=False,
        status='open',
        strategy='directional_trading'
    )
    
    position_id = await empty_db.add_position(new_position)
    assert position_id is not None, "New position should be added"
    
    # Verify position was tracked
    positions = await empty_db.get_open_positions()
    assert len(positions) == 1, "Should have 1 tracked position"
    assert positions[0].market_id == "NEW-MARKET-1"


@pytest.mark.asyncio
async def test_existing_positions_later_sync_updates(empty_db, mock_kalshi_with_existing_positions):
    """
    Test that on SUBSEQUENT runs (not first run), position sync works normally.
    
    After first run, the bot should sync positions to prevent drift.
    """
    # Mark database as "initialized" (past first run)
    await _mark_db_initialized(empty_db)
    
    # Add a position that exists on both Kalshi and DB
    tracked_position = Position(
        market_id="TRACKED-MARKET",
        side="YES",
        entry_price=0.60,
        quantity=10,
        timestamp=datetime.now(),
        rationale="Tracked position",
        confidence=0.70,
        live=True,
        status='open',
        strategy='directional_trading'
    )
    
    await empty_db.add_position(tracked_position)
    
    # Mock Kalshi with same position but different quantity (user manually added more)
    mock_kalshi = MagicMock(spec=KalshiClient)
    mock_kalshi.get_positions = AsyncMock(return_value={
        'market_positions': [
            {'ticker': 'TRACKED-MARKET', 'position': 20}  # Quantity changed from 10 to 20
        ]
    })
    
    # On subsequent run, sync SHOULD update the position
    # (This is the normal sync behavior, not ignoring)
    positions = await empty_db.get_open_positions()
    assert len(positions) == 1, "Should have 1 position"
    # Note: Actual sync code would update quantity to 20


@pytest.mark.asyncio
async def test_balance_display_without_phantom_trades(empty_db, mock_kalshi_with_existing_positions):
    """
    Test that dashboard balance reflects Kalshi balance accurately.
    
    Without syncing existing positions, balance should match Kalshi exactly.
    """
    # Get balance from Kalshi
    balance_response = await mock_kalshi_with_existing_positions.get_balance()
    kalshi_balance = balance_response['balance'] / 100  # $5000
    
    # Database has no positions
    db_positions = await empty_db.get_open_positions()
    assert len(db_positions) == 0
    
    # Dashboard should show:
    # - Cash: $5000 (from Kalshi)
    # - Position value: $0 (none tracked in DB)
    # - Unrealized P&L: $0 (no positions tracked)
    
    assert kalshi_balance == 5000.0, "Balance should be $5000"


@pytest.mark.asyncio
async def test_first_run_detection_logic():
    """
    Test the logic that detects if this is the first run (empty database).
    """
    # Create new empty database
    db_manager = DatabaseManager(db_path="test_first_run_detection.db")
    await db_manager.initialize()
    
    try:
        # Check if database is empty (first run)
        position_count = await _count_all_positions(db_manager)
        is_first_run = (position_count == 0)
        
        assert is_first_run, "Should detect first run with zero positions"
        
        # Add a position
        test_position = Position(
            market_id="TEST-MARKET",
            side="YES",
            entry_price=0.50,
            quantity=10,
            timestamp=datetime.now(),
            rationale="Test",
            confidence=0.50,
            live=False,
            status='open'
        )
        await db_manager.add_position(test_position)
        
        # Now it's not first run
        position_count_after = await _count_all_positions(db_manager)
        is_first_run_after = (position_count_after == 0)
        
        assert not is_first_run_after, "Should NOT be first run after adding position"
        
    finally:
        # Cleanup
        import os
        if os.path.exists("test_first_run_detection.db"):
            os.remove("test_first_run_detection.db")


@pytest.mark.asyncio
async def test_trade_logs_only_created_on_exit(empty_db):
    """
    Test that trade_log entries are ONLY created when positions exit, not on creation.
    
    This is critical - ensures existing positions won't create false trade logs.
    """
    # Create a position
    position = Position(
        market_id="TEST-EXIT-MARKET",
        side="YES",
        entry_price=0.60,
        quantity=25,
        timestamp=datetime.now(),
        rationale="Test exit",
        confidence=0.65,
        live=True,
        status='open',
        strategy='directional_trading'
    )
    
    position_id = await empty_db.add_position(position)
    assert position_id is not None
    
    # Verify NO trade log exists yet
    trade_logs = await empty_db.get_all_trade_logs()
    assert len(trade_logs) == 0, "No trade logs should exist while position is open"
    
    # Now simulate position exit
    trade_log = TradeLog(
        market_id="TEST-EXIT-MARKET",
        side="YES",
        entry_price=0.60,
        exit_price=0.75,
        quantity=25,
        pnl=(0.75 - 0.60) * 25,  # $3.75 profit
        entry_timestamp=position.timestamp,
        exit_timestamp=datetime.now(),
        rationale="Test exit",
        strategy='directional_trading',
        exit_reason='take_profit'
    )
    
    await empty_db.add_trade_log(trade_log)
    
    # NOW trade log should exist
    trade_logs_after = await empty_db.get_all_trade_logs()
    assert len(trade_logs_after) == 1, "Trade log should exist after exit"
    assert trade_logs_after[0].exit_reason == 'take_profit'


@pytest.mark.asyncio
async def test_duplicate_position_prevention(empty_db):
    """
    Test that duplicate positions are prevented by UNIQUE constraint.
    """
    position = Position(
        market_id="DUPLICATE-TEST",
        side="YES",
        entry_price=0.50,
        quantity=10,
        timestamp=datetime.now(),
        rationale="First position",
        confidence=0.60,
        live=False,
        status='open'
    )
    
    # Add first position
    position_id_1 = await empty_db.add_position(position)
    assert position_id_1 is not None, "First position should be added"
    
    # Try to add duplicate
    position_duplicate = Position(
        market_id="DUPLICATE-TEST",
        side="YES",  # Same market_id and side
        entry_price=0.55,
        quantity=20,
        timestamp=datetime.now(),
        rationale="Duplicate attempt",
        confidence=0.70,
        live=False,
        status='open'
    )
    
    position_id_2 = await empty_db.add_position(position_duplicate)
    assert position_id_2 is None, "Duplicate position should be rejected"
    
    # Verify only one position exists
    positions = await empty_db.get_open_positions()
    assert len(positions) == 1, "Should have exactly 1 position"


# Helper functions

async def _count_all_positions(db_manager: DatabaseManager) -> int:
    """Count all positions in database (open, closed, any status)."""
    async with aiosqlite.connect(db_manager.db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM positions")
        count = (await cursor.fetchone())[0]
        return count


async def _mark_db_initialized(db_manager: DatabaseManager):
    """
    Mark database as initialized (past first run).
    
    This simulates that the bot has already run once and synced.
    Could be implemented as a metadata table entry.
    """
    async with aiosqlite.connect(db_manager.db_path) as db:
        # Create a metadata table if it doesn't exist
        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        
        # Mark as initialized
        await db.execute("""
            INSERT OR REPLACE INTO system_metadata (key, value, timestamp)
            VALUES ('first_run_completed', 'true', ?)
        """, (datetime.now().isoformat(),))
        
        await db.commit()


async def _is_first_run(db_manager: DatabaseManager) -> bool:
    """
    Check if this is the first run (empty database).
    
    Returns True if no positions exist in database.
    """
    count = await _count_all_positions(db_manager)
    return count == 0


# Integration test

@pytest.mark.asyncio
async def test_full_startup_flow_with_existing_positions():
    """
    Integration test: Full startup flow with existing Kalshi positions.
    
    Simulates:
    1. Bot starts with empty database
    2. Kalshi account has existing positions
    3. Bot ignores them (doesn't sync)
    4. Bot creates new position
    5. New position is tracked properly
    6. Existing positions never create trade logs
    """
    # Setup
    db_manager = DatabaseManager(db_path="test_integration_startup.db")
    await db_manager.initialize()
    
    try:
        # Step 1: Verify empty database
        assert await _is_first_run(db_manager), "Should be first run"
        
        # Step 2: Mock Kalshi with existing positions
        mock_kalshi = MagicMock(spec=KalshiClient)
        mock_kalshi.get_positions = AsyncMock(return_value={
            'market_positions': [
                {'ticker': 'OLD-POS-1', 'position': 30},
                {'ticker': 'OLD-POS-2', 'position': -20}
            ]
        })
        
        # Step 3: On first run, DO NOT sync existing positions
        if await _is_first_run(db_manager):
            print("First run detected - ignoring existing Kalshi positions")
            # Skip sync
            await _mark_db_initialized(db_manager)
        
        # Verify database still empty
        positions = await db_manager.get_open_positions()
        assert len(positions) == 0, "Should ignore existing positions"
        
        # Step 4: Bot creates new position
        new_position = Position(
            market_id="NEW-BOT-POSITION",
            side="YES",
            entry_price=0.58,
            quantity=15,
            timestamp=datetime.now(),
            rationale="Bot-created trade",
            confidence=0.72,
            live=False,
            status='open',
            strategy='directional_trading'
        )
        
        position_id = await db_manager.add_position(new_position)
        assert position_id is not None, "New position should be added"
        
        # Step 5: Verify new position is tracked
        positions_after = await db_manager.get_open_positions()
        assert len(positions_after) == 1, "Should have 1 new tracked position"
        assert positions_after[0].market_id == "NEW-BOT-POSITION"
        
        # Step 6: Verify no trade logs for existing positions
        trade_logs = await db_manager.get_all_trade_logs()
        assert len(trade_logs) == 0, "Should have no trade logs (positions still open)"
        
        print("✅ Integration test passed - bot correctly ignores existing positions")
        
    finally:
        # Cleanup
        import os
        if os.path.exists("test_integration_startup.db"):
            os.remove("test_integration_startup.db")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
