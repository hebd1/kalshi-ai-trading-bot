"""
Tests for untracked position functionality.

Ensures that:
1. First run with empty DB marks existing Kalshi positions as untracked
2. Untracked positions are included in balance calculations
3. Untracked positions do NOT generate trade logs when closed
4. Tracked positions (new positions) DO generate trade logs when closed
5. Dashboard correctly handles both tracked and untracked positions
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.database import DatabaseManager, Position, TradeLog
from src.clients.kalshi_client import KalshiClient


@pytest.fixture
async def db_manager():
    """Create a test database manager."""
    db = DatabaseManager("test_untracked_positions.db")
    await db.initialize()
    yield db
    
    # Cleanup
    import os
    if os.path.exists("test_untracked_positions.db"):
        os.remove("test_untracked_positions.db")


@pytest.fixture
def mock_kalshi_client():
    """Create a mock Kalshi client."""
    client = MagicMock(spec=KalshiClient)
    
    # Mock existing positions on Kalshi (pre-deployment)
    client.get_positions = AsyncMock(return_value={
        'market_positions': [
            {'ticker': 'MARKET-001', 'position': 50},   # YES position (50 contracts)
            {'ticker': 'MARKET-002', 'position': -30},  # NO position (30 contracts)
        ]
    })
    
    # Mock market data for the existing positions
    async def mock_get_market(ticker):
        if ticker == 'MARKET-001':
            return {
                'market': {
                    'ticker': 'MARKET-001',
                    'yes_price': 6500,  # 65 cents
                    'no_price': 3500,
                    'status': 'active'
                }
            }
        elif ticker == 'MARKET-002':
            return {
                'market': {
                    'ticker': 'MARKET-002',
                    'yes_price': 3000,
                    'no_price': 7000,  # 70 cents
                    'status': 'active'
                }
            }
        return None
    
    client.get_market = AsyncMock(side_effect=mock_get_market)
    client.close = AsyncMock()
    
    return client


class TestUntrackedPositions:
    """Test suite for untracked position functionality."""
    
    @pytest.mark.asyncio
    async def test_first_run_detection_with_empty_db(self, db_manager):
        """Test that first run is correctly detected with empty database."""
        # Check position count
        import aiosqlite
        async with aiosqlite.connect(db_manager.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM positions")
            count = (await cursor.fetchone())[0]
            assert count == 0, "Database should be empty"
        
        # Check if first run marker exists
        async with aiosqlite.connect(db_manager.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            cursor = await db.execute(
                "SELECT value FROM system_metadata WHERE key = 'first_run_completed'"
            )
            marker = await cursor.fetchone()
            assert marker is None, "First run marker should not exist initially"
    
    @pytest.mark.asyncio
    async def test_mark_database_initialized(self, db_manager):
        """Test marking database as initialized."""
        async with aiosqlite.connect(db_manager.db_path) as db:
            # Create metadata table
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
            
            # Verify marker exists
            cursor = await db.execute(
                "SELECT value FROM system_metadata WHERE key = 'first_run_completed'"
            )
            marker = await cursor.fetchone()
            assert marker is not None, "First run marker should exist"
            assert marker[0] == 'true', "First run marker should be 'true'"
    
    @pytest.mark.asyncio
    async def test_untracked_position_creation(self, db_manager, mock_kalshi_client):
        """Test that existing Kalshi positions are created as untracked in empty DB."""
        # Simulate first run - fetch Kalshi positions and create as untracked
        positions_response = await mock_kalshi_client.get_positions()
        kalshi_positions = positions_response.get('market_positions', [])
        
        for pos in kalshi_positions:
            ticker = pos.get('ticker')
            position_count = pos.get('position', 0)
            
            if ticker and position_count != 0:
                market_data = await mock_kalshi_client.get_market(ticker)
                market_info = market_data['market']
                
                if position_count > 0:  # YES
                    side = 'YES'
                    price = market_info['yes_price'] / 100
                else:  # NO
                    side = 'NO'
                    price = market_info['no_price'] / 100
                
                # Create untracked position
                untracked_pos = Position(
                    market_id=ticker,
                    side=side,
                    entry_price=price,
                    quantity=abs(position_count),
                    timestamp=datetime.now(),
                    rationale="Pre-existing position (untracked for P&L)",
                    confidence=0.5,
                    live=True,
                    status='open',
                    strategy='legacy_untracked',
                    tracked=False  # KEY: marked as untracked
                )
                
                await db_manager.add_position(untracked_pos)
        
        # Verify positions were created
        positions = await db_manager.get_open_positions()
        assert len(positions) == 2, "Should have 2 untracked positions"
        
        # Verify all positions are marked as untracked
        for pos in positions:
            assert pos.tracked == False, f"Position {pos.market_id} should be untracked"
            assert pos.strategy == 'legacy_untracked', f"Position {pos.market_id} should have legacy_untracked strategy"
            assert "Pre-existing" in pos.rationale, f"Position {pos.market_id} should have pre-existing rationale"
    
    @pytest.mark.asyncio
    async def test_untracked_position_in_balance_calculation(self, db_manager, mock_kalshi_client):
        """Test that untracked positions are included in balance calculations."""
        # Create untracked position
        untracked_pos = Position(
            market_id='MARKET-001',
            side='YES',
            entry_price=0.65,
            quantity=50,
            timestamp=datetime.now(),
            rationale="Pre-existing position",
            live=True,
            status='open',
            tracked=False
        )
        await db_manager.add_position(untracked_pos)
        
        # Get positions for balance calculation
        positions = await db_manager.get_open_positions()
        
        # Calculate position value (as dashboard would do)
        total_position_value = sum(
            pos.quantity * pos.entry_price for pos in positions
        )
        
        expected_value = 50 * 0.65  # 50 contracts at 65 cents = $32.50
        assert abs(total_position_value - expected_value) < 0.01, \
            f"Position value should be ${expected_value}, got ${total_position_value}"
    
    @pytest.mark.asyncio
    async def test_untracked_position_no_trade_log_on_close(self, db_manager):
        """Test that untracked positions do NOT create trade logs when closed."""
        # Create untracked position
        untracked_pos = Position(
            market_id='MARKET-001',
            side='YES',
            entry_price=0.65,
            quantity=50,
            timestamp=datetime.now(),
            rationale="Pre-existing position",
            live=True,
            status='open',
            strategy='legacy_untracked',
            tracked=False
        )
        pos_id = await db_manager.add_position(untracked_pos)
        
        # Simulate closing the position (as track.py would do)
        # For untracked positions, we just update status without creating trade log
        await db_manager.update_position_status(pos_id, 'closed')
        
        # Verify position is closed
        import aiosqlite
        async with aiosqlite.connect(db_manager.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT status FROM positions WHERE id = ?", (pos_id,)
            )
            row = await cursor.fetchone()
            assert row['status'] == 'closed', "Position should be closed"
        
        # Verify NO trade log was created
        trade_logs = await db_manager.get_all_trade_logs()
        assert len(trade_logs) == 0, "No trade log should be created for untracked position"
    
    @pytest.mark.asyncio
    async def test_tracked_position_creates_trade_log_on_close(self, db_manager):
        """Test that tracked positions DO create trade logs when closed."""
        # Create TRACKED position (new position from bot)
        tracked_pos = Position(
            market_id='MARKET-003',
            side='YES',
            entry_price=0.45,
            quantity=100,
            timestamp=datetime.now(),
            rationale="Bot-created position",
            live=True,
            status='open',
            strategy='directional_trading',
            tracked=True  # Explicitly tracked
        )
        pos_id = await db_manager.add_position(tracked_pos)
        
        # Simulate closing with trade log (as track.py would do)
        exit_price = 0.55
        pnl = (exit_price - tracked_pos.entry_price) * tracked_pos.quantity
        
        trade_log = TradeLog(
            market_id=tracked_pos.market_id,
            side=tracked_pos.side,
            entry_price=tracked_pos.entry_price,
            exit_price=exit_price,
            quantity=tracked_pos.quantity,
            pnl=pnl,
            entry_timestamp=tracked_pos.timestamp,
            exit_timestamp=datetime.now(),
            rationale=tracked_pos.rationale,
            strategy=tracked_pos.strategy,
            exit_reason='take_profit'
        )
        
        await db_manager.add_trade_log(trade_log)
        await db_manager.update_position_status(pos_id, 'closed')
        
        # Verify trade log WAS created
        trade_logs = await db_manager.get_all_trade_logs()
        assert len(trade_logs) == 1, "Trade log should be created for tracked position"
        assert trade_logs[0].pnl == pnl, f"P&L should be ${pnl}"
    
    @pytest.mark.asyncio
    async def test_mixed_tracked_and_untracked_positions(self, db_manager):
        """Test system with both tracked and untracked positions."""
        # Create untracked (legacy) position
        untracked_pos = Position(
            market_id='LEGACY-001',
            side='YES',
            entry_price=0.60,
            quantity=50,
            timestamp=datetime.now(),
            rationale="Pre-existing",
            live=True,
            status='open',
            tracked=False
        )
        await db_manager.add_position(untracked_pos)
        
        # Create tracked (new) position
        tracked_pos = Position(
            market_id='NEW-001',
            side='NO',
            entry_price=0.40,
            quantity=100,
            timestamp=datetime.now(),
            rationale="Bot-created",
            live=True,
            status='open',
            tracked=True
        )
        await db_manager.add_position(tracked_pos)
        
        # Get all positions
        positions = await db_manager.get_open_positions()
        assert len(positions) == 2, "Should have 2 positions"
        
        # Verify tracked status
        tracked_count = sum(1 for p in positions if p.tracked)
        untracked_count = sum(1 for p in positions if not p.tracked)
        
        assert tracked_count == 1, "Should have 1 tracked position"
        assert untracked_count == 1, "Should have 1 untracked position"
        
        # Calculate total position value (both should be included)
        total_value = sum(p.quantity * p.entry_price for p in positions)
        expected_value = (50 * 0.60) + (100 * 0.40)  # $30 + $40 = $70
        assert abs(total_value - expected_value) < 0.01, \
            f"Total value should be ${expected_value}, got ${total_value}"
    
    @pytest.mark.asyncio
    async def test_performance_metrics_exclude_untracked(self, db_manager):
        """Test that performance metrics exclude untracked positions."""
        # Create untracked position and close it (no trade log)
        untracked_pos = Position(
            market_id='LEGACY-001',
            side='YES',
            entry_price=0.60,
            quantity=50,
            timestamp=datetime.now(),
            rationale="Pre-existing",
            live=True,
            status='open',
            tracked=False,
            strategy='legacy_untracked'
        )
        untracked_id = await db_manager.add_position(untracked_pos)
        await db_manager.update_position_status(untracked_id, 'closed')
        
        # Create tracked position and close it (with trade log)
        tracked_pos = Position(
            market_id='NEW-001',
            side='NO',
            entry_price=0.40,
            quantity=100,
            timestamp=datetime.now(),
            rationale="Bot-created",
            live=True,
            status='open',
            tracked=True,
            strategy='directional_trading'
        )
        tracked_id = await db_manager.add_position(tracked_pos)
        
        # Create trade log for tracked position
        trade_log = TradeLog(
            market_id=tracked_pos.market_id,
            side=tracked_pos.side,
            entry_price=tracked_pos.entry_price,
            exit_price=0.50,
            quantity=tracked_pos.quantity,
            pnl=10.0,  # $10 profit
            entry_timestamp=tracked_pos.timestamp,
            exit_timestamp=datetime.now(),
            rationale=tracked_pos.rationale,
            strategy=tracked_pos.strategy
        )
        await db_manager.add_trade_log(trade_log)
        await db_manager.update_position_status(tracked_id, 'closed')
        
        # Get performance by strategy
        performance = await db_manager.get_performance_by_strategy()
        
        # Verify untracked positions don't appear in performance
        assert 'legacy_untracked' not in performance or performance['legacy_untracked']['completed_trades'] == 0, \
            "Untracked strategy should have no completed trades"
        
        # Verify tracked position appears in performance
        assert 'directional_trading' in performance, "Tracked strategy should appear"
        assert performance['directional_trading']['completed_trades'] == 1, \
            "Should have 1 completed tracked trade"
        assert performance['directional_trading']['total_pnl'] == 10.0, \
            "P&L should only include tracked trades"
    
    @pytest.mark.asyncio
    async def test_subsequent_runs_track_new_positions(self, db_manager):
        """Test that after first run, new positions are tracked by default."""
        # Simulate database already initialized (not first run)
        import aiosqlite
        async with aiosqlite.connect(db_manager.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT OR REPLACE INTO system_metadata (key, value, timestamp)
                VALUES ('first_run_completed', 'true', ?)
            """, (datetime.now().isoformat(),))
            await db.commit()
        
        # Create new position (should be tracked by default)
        new_pos = Position(
            market_id='NEW-002',
            side='YES',
            entry_price=0.55,
            quantity=75,
            timestamp=datetime.now(),
            rationale="Bot-created after first run",
            live=True,
            status='open',
            strategy='directional_trading'
            # tracked=True is default
        )
        await db_manager.add_position(new_pos)
        
        # Verify position is tracked
        positions = await db_manager.get_open_positions()
        assert len(positions) == 1, "Should have 1 position"
        assert positions[0].tracked == True, "New position should be tracked by default"


class TestUntrackedPositionIntegration:
    """Integration tests for untracked position workflow."""
    
    @pytest.mark.asyncio
    async def test_full_first_run_workflow(self, db_manager, mock_kalshi_client):
        """Test complete first-run workflow with untracked positions."""
        # 1. Empty database check
        import aiosqlite
        async with aiosqlite.connect(db_manager.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM positions")
            count = (await cursor.fetchone())[0]
            assert count == 0, "Database should be empty initially"
        
        # 2. Fetch existing Kalshi positions
        positions_response = await mock_kalshi_client.get_positions()
        kalshi_positions = positions_response.get('market_positions', [])
        assert len(kalshi_positions) == 2, "Should have 2 Kalshi positions"
        
        # 3. Create untracked positions for existing Kalshi positions
        for pos in kalshi_positions:
            ticker = pos.get('ticker')
            position_count = pos.get('position', 0)
            
            if ticker and position_count != 0:
                market_data = await mock_kalshi_client.get_market(ticker)
                market_info = market_data['market']
                
                if position_count > 0:
                    side = 'YES'
                    price = market_info['yes_price'] / 100
                else:
                    side = 'NO'
                    price = market_info['no_price'] / 100
                
                untracked_pos = Position(
                    market_id=ticker,
                    side=side,
                    entry_price=price,
                    quantity=abs(position_count),
                    timestamp=datetime.now(),
                    rationale="Pre-existing position (untracked for P&L)",
                    confidence=0.5,
                    live=True,
                    status='open',
                    strategy='legacy_untracked',
                    tracked=False
                )
                
                await db_manager.add_position(untracked_pos)
        
        # 4. Mark database as initialized
        async with aiosqlite.connect(db_manager.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT OR REPLACE INTO system_metadata (key, value, timestamp)
                VALUES ('first_run_completed', 'true', ?)
            """, (datetime.now().isoformat(),))
            await db.commit()
        
        # 5. Verify all positions are untracked
        positions = await db_manager.get_open_positions()
        assert len(positions) == 2, "Should have 2 positions"
        assert all(not p.tracked for p in positions), "All positions should be untracked"
        
        # 6. Create a NEW tracked position (bot-created)
        new_pos = Position(
            market_id='NEW-MARKET',
            side='YES',
            entry_price=0.50,
            quantity=100,
            timestamp=datetime.now(),
            rationale="Bot-created position",
            live=True,
            status='open',
            strategy='directional_trading',
            tracked=True
        )
        await db_manager.add_position(new_pos)
        
        # 7. Verify mix of tracked and untracked
        all_positions = await db_manager.get_open_positions()
        assert len(all_positions) == 3, "Should have 3 total positions"
        
        tracked_positions = [p for p in all_positions if p.tracked]
        untracked_positions = [p for p in all_positions if not p.tracked]
        
        assert len(tracked_positions) == 1, "Should have 1 tracked position"
        assert len(untracked_positions) == 2, "Should have 2 untracked positions"
        
        # 8. Calculate balance (should include all)
        total_value = sum(p.quantity * p.entry_price for p in all_positions)
        expected = (50 * 0.65) + (30 * 0.70) + (100 * 0.50)  # $32.50 + $21 + $50 = $103.50
        assert abs(total_value - expected) < 0.01, f"Total should be ${expected}"
        
        # 9. Close untracked position (no trade log)
        untracked_to_close = untracked_positions[0]
        await db_manager.update_position_status(untracked_to_close.id, 'closed')
        
        trade_logs = await db_manager.get_all_trade_logs()
        assert len(trade_logs) == 0, "No trade log for untracked position"
        
        # 10. Close tracked position (with trade log)
        tracked_to_close = tracked_positions[0]
        trade_log = TradeLog(
            market_id=tracked_to_close.market_id,
            side=tracked_to_close.side,
            entry_price=tracked_to_close.entry_price,
            exit_price=0.60,
            quantity=tracked_to_close.quantity,
            pnl=10.0,
            entry_timestamp=tracked_to_close.timestamp,
            exit_timestamp=datetime.now(),
            rationale=tracked_to_close.rationale,
            strategy=tracked_to_close.strategy,
            exit_reason='take_profit'
        )
        await db_manager.add_trade_log(trade_log)
        await db_manager.update_position_status(tracked_to_close.id, 'closed')
        
        trade_logs = await db_manager.get_all_trade_logs()
        assert len(trade_logs) == 1, "Should have 1 trade log for tracked position"
        
        # 11. Verify performance metrics
        performance = await db_manager.get_performance_by_strategy()
        
        # Untracked should have no P&L
        if 'legacy_untracked' in performance:
            assert performance['legacy_untracked']['completed_trades'] == 0, \
                "Untracked strategy should have no recorded trades"
        
        # Tracked should have P&L
        assert 'directional_trading' in performance, "Tracked strategy should appear"
        assert performance['directional_trading']['completed_trades'] == 1, \
            "Should have 1 completed trade"
        assert performance['directional_trading']['total_pnl'] == 10.0, \
            "P&L should be $10"


if __name__ == "__main__":
    # Run tests
    import sys
    pytest.main([__file__, "-v", "-s"] + sys.argv[1:])
