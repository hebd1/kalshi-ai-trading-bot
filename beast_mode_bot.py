#!/usr/bin/env python3
"""
Beast Mode Trading Bot 🚀

Main entry point for the Unified Advanced Trading System that orchestrates:
- Market Making Strategy (40% allocation)
- Directional Trading with Portfolio Optimization (50% allocation) 
- Arbitrage Detection (10% allocation)

Features:
- No time restrictions (trade any deadline)
- Dynamic exit strategies
- Kelly Criterion portfolio optimization
- Real-time risk management
- Market making for spread profits

Usage:
    python beast_mode_bot.py              # Paper trading mode
    python beast_mode_bot.py --live       # Live trading mode
    python beast_mode_bot.py --dashboard  # Live dashboard mode
"""

import asyncio
import argparse
import time
import signal
from datetime import datetime, timedelta
from typing import Optional

from src.jobs.trade import run_trading_job
from src.jobs.ingest import run_ingestion
from src.jobs.track import run_tracking
from src.jobs.evaluate import run_evaluation
from src.utils.logging_setup import setup_logging, get_trading_logger
from src.utils.database import DatabaseManager, Position
from src.clients.kalshi_client import KalshiClient
from src.clients.xai_client import XAIClient
from src.config.settings import settings

# Import Beast Mode components
from src.strategies.unified_trading_system import run_unified_trading_system, TradingSystemConfig
from beast_mode_dashboard import BeastModeDashboard


class BeastModeBot:
    """
    Beast Mode Trading Bot - Advanced Multi-Strategy Trading System 🚀
    
    This bot orchestrates all advanced strategies:
    1. Market Making (spread profits)
    2. Directional Trading (AI predictions with portfolio optimization)
    3. Arbitrage Detection (future feature)
    
    Features:
    - Unlimited market deadlines with dynamic exits
    - Cost controls and budget management
    - Real-time performance monitoring
    - Risk management and rebalancing
    """
    
    def __init__(self, live_mode: bool = False, dashboard_mode: bool = False):
        # Auto-detect trading mode from environment if not explicitly set
        if not live_mode:
            env_mode = settings.api.get_trading_mode_from_env()
            live_mode = (env_mode == "live")
        
        self.live_mode = live_mode
        self.dashboard_mode = dashboard_mode
        self.logger = get_trading_logger("beast_mode_bot")
        self.shutdown_event = asyncio.Event()
        
        # Configure environment (PROD vs TEST credentials)
        settings.api.configure_environment(use_live=live_mode)
        
        # Set live trading in settings
        settings.trading.live_trading_enabled = live_mode
        settings.trading.paper_trading_mode = not live_mode
        
        self.logger.info(
            f"🚀 Beast Mode Bot initialized - "
            f"Mode: {'LIVE TRADING' if live_mode else 'PAPER TRADING'}"
        )
        self.logger.info(
            f"🔑 Environment: {'PROD' if live_mode else 'DEMO'} "
            f"({settings.api.kalshi_base_url})"
        )
        
        # Log explicit warning for live trading
        if live_mode:
            self.logger.warning("⚠️  LIVE TRADING MODE ENABLED - USING REAL MONEY!")
            self.logger.warning("⚠️  Ensure production API credentials are correctly configured!")

    async def run_dashboard_mode(self):
        """Run in live dashboard mode with real-time updates."""
        try:
            self.logger.info("🚀 Starting Beast Mode Dashboard Mode")
            dashboard = BeastModeDashboard()
            await dashboard.show_live_dashboard()
        except KeyboardInterrupt:
            self.logger.info("👋 Dashboard mode stopped")
        except Exception as e:
            self.logger.error(f"Error in dashboard mode: {e}")

    async def run_trading_mode(self):
        """Run the Beast Mode trading system with all strategies."""
        try:
            self.logger.info("🚀 BEAST MODE TRADING BOT STARTED")
            self.logger.info(f"📊 Trading Mode: {'LIVE' if self.live_mode else 'PAPER'}")
            self.logger.info(f"💰 Daily AI Budget: ${settings.trading.daily_ai_budget}")
            self.logger.info(f"⚡ Features: Market Making + Portfolio Optimization + Dynamic Exits")
            
            # 🚨 CRITICAL FIX: Initialize database FIRST and wait for completion
            self.logger.info("🔧 Initializing database...")
            db_manager = DatabaseManager()
            await self._ensure_database_ready(db_manager)
            self.logger.info("✅ Database initialization complete!")
            
            # Initialize other components
            kalshi_client = KalshiClient(db_manager=db_manager)  # Pass db_manager for latency tracking
            xai_client = XAIClient(db_manager=db_manager)  # Pass db_manager for LLM logging
            
            # 🔄 Sync actual positions and balance from Kalshi on startup
            self.logger.info("🔄 Syncing positions and balance from Kalshi...")
            await self._sync_positions_and_balance(db_manager, kalshi_client)
            self.logger.info("✅ Position sync complete!")
            
            # Small delay to ensure everything is ready
            await asyncio.sleep(1)
            
            # Start market ingestion first
            self.logger.info("🔄 Starting market ingestion...")
            ingestion_task = asyncio.create_task(self._run_market_ingestion(db_manager, kalshi_client))
            
            # Wait for initial market data ingestion
            await asyncio.sleep(10)
            
            # Run remaining background tasks
            self.logger.info("🚀 Starting trading and monitoring tasks...")
            tasks = [
                ingestion_task,  # Already started
                asyncio.create_task(self._run_trading_cycles(db_manager, kalshi_client, xai_client)),
                asyncio.create_task(self._run_position_tracking(db_manager, kalshi_client)),
                asyncio.create_task(self._run_performance_evaluation(db_manager)),
                asyncio.create_task(self._run_balance_tracking(db_manager, kalshi_client))  # NEW: Balance tracking
            ]
            
            # Setup shutdown handler
            def signal_handler():
                self.logger.info("🛑 Shutdown signal received")
                self.shutdown_event.set()
                for task in tasks:
                    task.cancel()
            
            # Handle Ctrl+C gracefully
            for sig in [signal.SIGINT, signal.SIGTERM]:
                signal.signal(sig, lambda s, f: signal_handler())
            
            # Wait for shutdown or completion
            await asyncio.gather(*tasks, return_exceptions=True)
            
            await xai_client.close()
            await kalshi_client.close()
            
            self.logger.info("🏁 Beast Mode Bot shut down gracefully")
            
        except Exception as e:
            self.logger.error(f"Error in Beast Mode Bot: {e}")
            raise

    async def _ensure_database_ready(self, db_manager: DatabaseManager):
        """Ensure database is fully initialized before starting any tasks."""
        try:
            # Initialize the database first to create all tables
            await db_manager.initialize()
            
            # Verify tables exist by checking one of them
            import aiosqlite
            async with aiosqlite.connect(db_manager.db_path) as db:
                await db.execute("SELECT COUNT(*) FROM positions LIMIT 1")
                await db.execute("SELECT COUNT(*) FROM markets LIMIT 1") 
                await db.execute("SELECT COUNT(*) FROM trade_logs LIMIT 1")
            
            self.logger.info("🎯 Database tables verified and ready")
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise

    async def _sync_positions_and_balance(self, db_manager: DatabaseManager, kalshi_client: KalshiClient):
        """
        Sync actual positions and balance from Kalshi on startup.
        
        This method ensures the database accurately reflects reality by:
        1. Detecting if this is first run (empty database)
        2. On FIRST run: Ignores existing Kalshi positions (pre-bot deployment)
        3. On SUBSEQUENT runs: Syncs positions to prevent drift
        4. Marking any DB positions NOT on Kalshi as 'closed'
        5. Upserting tracked Kalshi positions into the database
        """
        try:
            import aiosqlite
            
            # Get current balance
            balance_response = await kalshi_client.get_balance()
            balance = balance_response.get('balance', 0) / 100
            self.logger.info(f"💰 Current balance: ${balance:.2f}")
            
            # 🚨 CRITICAL: Check if this is the FIRST RUN (empty database)
            position_count = await self._count_all_positions(db_manager)
            is_first_run = (position_count == 0)
            
            if is_first_run:
                self.logger.warning("=" * 60)
                self.logger.warning("🔔 FIRST RUN DETECTED - Empty Database")
                self.logger.warning("=" * 60)
                self.logger.warning("ℹ️  Bot will mark existing Kalshi positions as UNTRACKED")
                self.logger.warning("ℹ️  Untracked positions: included in balance, excluded from P&L")
                self.logger.warning("ℹ️  Only NEW positions created by bot will generate trade logs")
                self.logger.warning("=" * 60)
                
                # Mark database as initialized
                await self._mark_database_initialized(db_manager)
                
                # Get existing positions from Kalshi and mark as untracked
                positions_response = await kalshi_client.get_positions()
                market_positions = positions_response.get('market_positions', [])
                
                existing_count = sum(1 for pos in market_positions if pos.get('position', 0) != 0)
                if existing_count > 0:
                    self.logger.info(f"📊 Found {existing_count} existing Kalshi positions - marking as UNTRACKED")
                    
                    # Sync existing positions but mark them as untracked
                    for pos in market_positions:
                        ticker = pos.get('ticker')
                        position_count = pos.get('position', 0)
                        
                        if ticker and position_count != 0:
                            try:
                                market_data = await kalshi_client.get_market(ticker)
                                if market_data and 'market' in market_data:
                                    market_info = market_data['market']
                                    
                                    if position_count > 0:  # YES position
                                        side = 'YES'
                                        current_price = market_info.get('yes_price', 50) / 100
                                    else:  # NO position
                                        side = 'NO'
                                        current_price = market_info.get('no_price', 50) / 100
                                    
                                    # Create untracked position
                                    untracked_position = Position(
                                        market_id=ticker,
                                        side=side,
                                        entry_price=current_price,
                                        quantity=abs(position_count),
                                        timestamp=datetime.now(),
                                        rationale="Pre-existing position (untracked for P&L)",
                                        confidence=0.5,
                                        live=True,
                                        status='open',
                                        strategy='legacy_untracked',
                                        tracked=False  # Mark as untracked
                                    )
                                    
                                    await db_manager.add_position(untracked_position)
                                    self.logger.info(f"   ✅ Synced UNTRACKED: {ticker} {side} ({abs(position_count)} contracts)")
                                    
                            except Exception as e:
                                self.logger.warning(f"Could not sync untracked position {ticker}: {e}")
                    
                    self.logger.info("✅ Existing positions synced as UNTRACKED")
                    self.logger.info("✅ These will be included in balance but NOT in P&L calculations")
                    self.logger.info("✅ No trade logs will be created when they close")
                else:
                    self.logger.info("📊 No existing Kalshi positions found")
                
                self.logger.info("🚀 First run initialization complete - ready for trading!")
                return  # Exit after marking existing positions as untracked
            
            # Get current positions from Kalshi (the REAL source of truth)
            positions_response = await kalshi_client.get_positions()
            market_positions = positions_response.get('market_positions', [])
            
            # Build set of active Kalshi market IDs (only those with non-zero positions)
            kalshi_active_markets = set()
            for pos in market_positions:
                ticker = pos.get('ticker')
                position_count = pos.get('position', 0)
                if ticker and position_count != 0:
                    kalshi_active_markets.add(ticker)
            
            self.logger.info(f"📊 Kalshi has {len(kalshi_active_markets)} active positions")
            
            # Step 1: Mark any DB positions NOT on Kalshi as 'closed'
            async with aiosqlite.connect(db_manager.db_path) as db:
                # Get all open positions from database
                cursor = await db.execute("SELECT id, market_id, side FROM positions WHERE status = 'open'")
                db_open_positions = await cursor.fetchall()
                
                closed_count = 0
                for pos_row in db_open_positions:
                    pos_id, market_id, side = pos_row
                    if market_id not in kalshi_active_markets:
                        # This position doesn't exist on Kalshi anymore - mark as closed
                        await db.execute(
                            "UPDATE positions SET status = 'closed' WHERE id = ?",
                            (pos_id,)
                        )
                        closed_count += 1
                        self.logger.info(f"   🔄 Marked as closed (not on Kalshi): {market_id} {side}")
                
                if closed_count > 0:
                    await db.commit()
                    self.logger.info(f"🗑️  Closed {closed_count} stale positions not found on Kalshi")
            
            # Step 2: Upsert all Kalshi positions
            if not kalshi_active_markets:
                self.logger.info("📊 No active positions on Kalshi")
                return
            
            synced_count = 0
            updated_count = 0
            
            for kalshi_pos in market_positions:
                ticker = kalshi_pos.get('ticker')
                position_count = kalshi_pos.get('position', 0)
                
                if ticker and position_count != 0:
                    try:
                        # Get market data for pricing
                        market_data = await kalshi_client.get_market(ticker)
                        if market_data and 'market' in market_data:
                            market_info = market_data['market']
                            
                            # Determine side and current price
                            if position_count > 0:  # YES position
                                side = 'YES'
                                current_price = market_info.get('yes_price', 50) / 100
                            else:  # NO position
                                side = 'NO'
                                current_price = market_info.get('no_price', 50) / 100
                            
                            # Check if position already exists in DB (including closed positions!)
                            # First check for open position
                            existing_position = await db_manager.get_position_by_market_and_side(ticker, side)
                            
                            if existing_position:
                                # Update existing OPEN position to ensure quantity is correct
                                async with aiosqlite.connect(db_manager.db_path) as db:
                                    await db.execute(
                                        "UPDATE positions SET status = 'open', live = 1, quantity = ? WHERE id = ?",
                                        (abs(position_count), existing_position.id)
                                    )
                                    await db.commit()
                                updated_count += 1
                                self.logger.debug(f"   🔄 Updated open: {ticker} - {side} {abs(position_count)}")
                            else:
                                # Check for ANY existing position (including closed) due to UNIQUE constraint
                                async with aiosqlite.connect(db_manager.db_path) as db:
                                    cursor = await db.execute(
                                        "SELECT id FROM positions WHERE market_id = ? AND side = ?",
                                        (ticker, side)
                                    )
                                    existing_any = await cursor.fetchone()
                                    
                                    if existing_any:
                                        # Reopen the closed position
                                        await db.execute(
                                            "UPDATE positions SET status = 'open', live = 1, quantity = ?, entry_price = ? WHERE id = ?",
                                            (abs(position_count), current_price, existing_any[0])
                                        )
                                        await db.commit()
                                        updated_count += 1
                                        self.logger.info(f"   🔄 Reopened closed: {ticker} - {side} {abs(position_count)} @ ${current_price:.2f}")
                                    else:
                                        # Truly new position - create it
                                        position = Position(
                                            market_id=ticker,
                                            side=side,
                                            entry_price=current_price,
                                            quantity=abs(position_count),
                                            timestamp=datetime.now(),
                                            rationale="Synced from Kalshi on startup",
                                            confidence=0.5,
                                            live=True,
                                            status='open',
                                            strategy='startup_sync'
                                        )
                                        
                                        # Add to database directly (bypass the duplicate check since we just did it)
                                        position_dict = {
                                            'market_id': ticker,
                                            'side': side,
                                            'entry_price': current_price,
                                            'quantity': abs(position_count),
                                            'timestamp': datetime.now().isoformat(),
                                            'rationale': "Synced from Kalshi on startup",
                                            'confidence': 0.5,
                                            'live': True,
                                            'status': 'open',
                                            'strategy': 'startup_sync',
                                            'stop_loss_price': None,
                                            'take_profit_price': None,
                                            'max_hold_hours': None,
                                            'target_confidence_change': None
                                        }
                                        await db.execute("""
                                            INSERT INTO positions (market_id, side, entry_price, quantity, timestamp, rationale, confidence, live, status, strategy, stop_loss_price, take_profit_price, max_hold_hours, target_confidence_change)
                                            VALUES (:market_id, :side, :entry_price, :quantity, :timestamp, :rationale, :confidence, :live, :status, :strategy, :stop_loss_price, :take_profit_price, :max_hold_hours, :target_confidence_change)
                                        """, position_dict)
                                        await db.commit()
                                        synced_count += 1
                                        self.logger.info(f"   ✅ Synced new: {ticker} - {side} {abs(position_count)} @ ${current_price:.2f}")
                    
                    except Exception as e:
                        self.logger.warning(f"Could not sync position {ticker}: {e}")
            
            self.logger.info(f"✅ Sync complete: {synced_count} new, {updated_count} updated positions")
            
        except Exception as e:
            self.logger.error(f"Error syncing positions: {e}")

    async def _count_all_positions(self, db_manager: DatabaseManager) -> int:
        """
        Count all positions in database (any status).
        Used to detect first run.
        """
        import aiosqlite
        async with aiosqlite.connect(db_manager.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM positions")
            count = (await cursor.fetchone())[0]
            return count

    async def _mark_database_initialized(self, db_manager: DatabaseManager):
        """
        Mark database as initialized (past first run).
        Creates metadata record to track initialization.
        """
        import aiosqlite
        async with aiosqlite.connect(db_manager.db_path) as db:
            # Create metadata table if it doesn't exist
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

    async def _run_market_ingestion(self, db_manager: DatabaseManager, kalshi_client: KalshiClient):
        """Background task for market data ingestion."""
        while not self.shutdown_event.is_set():
            try:
                # Create a queue for market ingestion (though we're not using it in Beast Mode)
                market_queue = asyncio.Queue()
                # ✅ FIXED: Pass the shared database manager
                await run_ingestion(db_manager, market_queue)
                await asyncio.sleep(300)  # Run every 5 minutes (much slower to prevent 429s)
            except Exception as e:
                self.logger.error(f"Error in market ingestion: {e}")
                await asyncio.sleep(60)

    async def _run_trading_cycles(self, db_manager: DatabaseManager, kalshi_client: KalshiClient, xai_client: XAIClient):
        """Main Beast Mode trading cycles."""
        cycle_count = 0
        
        while not self.shutdown_event.is_set():
            try:
                # Check daily AI cost limits before starting cycle
                if not await self._check_daily_ai_limits(xai_client):
                    # Sleep until next day if limits reached
                    await self._sleep_until_next_day()
                    continue
                
                cycle_count += 1
                self.logger.info(f"🔄 Starting Beast Mode Trading Cycle #{cycle_count}")
                
                # Run the Beast Mode unified trading system
                results = await run_trading_job()
                
                if results and results.total_positions > 0:
                    self.logger.info(
                        f"✅ Cycle #{cycle_count} Complete - "
                        f"Positions: {results.total_positions}, "
                        f"Capital Used: ${results.total_capital_used:.0f} ({results.capital_efficiency:.1%}), "
                        f"Expected Return: {results.expected_annual_return:.1%}"
                    )
                else:
                    self.logger.info(f"📊 Cycle #{cycle_count} Complete - No new positions created")
                
                # Wait for next cycle (60 seconds)
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in trading cycle #{cycle_count}: {e}")
                await asyncio.sleep(60)

    async def _check_daily_ai_limits(self, xai_client: XAIClient) -> bool:
        """
        Check if we should continue trading based on daily AI cost limits.
        Returns True if we can continue, False if we should pause.
        """
        if not settings.trading.enable_daily_cost_limiting:
            return True
        
        # Check daily tracker in xAI client
        if hasattr(xai_client, 'daily_tracker') and xai_client.daily_tracker.is_exhausted:
            self.logger.warning(
                "🚫 Daily AI cost limit reached - trading paused",
                daily_cost=xai_client.daily_tracker.total_cost,
                daily_limit=xai_client.daily_tracker.daily_limit,
                requests_today=xai_client.daily_tracker.request_count
            )
            return False
        
        return True

    async def _sleep_until_next_day(self):
        """Sleep until the next day (midnight) when daily limits reset."""
        if not settings.trading.sleep_when_limit_reached:
            # Just sleep for a normal cycle if sleep is disabled
            await asyncio.sleep(60)
            return
        
        # Calculate time until next day
        now = datetime.now()
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_next_day = (next_day - now).total_seconds()
        
        # Ensure we don't sleep for more than 24 hours (safety check)
        max_sleep = 24 * 60 * 60  # 24 hours
        sleep_time = min(seconds_until_next_day, max_sleep)
        
        if sleep_time > 0:
            hours_to_sleep = sleep_time / 3600
            self.logger.info(
                f"💤 Sleeping until next day to reset AI limits - {hours_to_sleep:.1f} hours"
            )
            
            # Sleep in chunks to allow for graceful shutdown
            chunk_size = 300  # 5 minutes per chunk
            while sleep_time > 0 and not self.shutdown_event.is_set():
                current_chunk = min(chunk_size, sleep_time)
                await asyncio.sleep(current_chunk)
                sleep_time -= current_chunk
            
            self.logger.info("🌅 Daily AI limits reset - resuming trading")
        else:
            # Safety fallback
            await asyncio.sleep(60)

    async def _run_position_tracking(self, db_manager: DatabaseManager, kalshi_client: KalshiClient):
        """Background task for position tracking and exit strategies."""
        while not self.shutdown_event.is_set():
            try:
                # ✅ FIXED: Pass the shared database manager
                await run_tracking(db_manager)
                await asyncio.sleep(120)  # Check positions every 2 minutes (slower to reduce API load)
            except Exception as e:
                self.logger.error(f"Error in position tracking: {e}")
                await asyncio.sleep(30)

    async def _run_performance_evaluation(self, db_manager: DatabaseManager):
        """Background task for performance evaluation."""
        while not self.shutdown_event.is_set():
            try:
                await run_evaluation()
                await asyncio.sleep(300)  # Run every 5 minutes
            except Exception as e:
                self.logger.error(f"Error in performance evaluation: {e}")
                await asyncio.sleep(300)

    async def _run_balance_tracking(self, db_manager: DatabaseManager, kalshi_client: KalshiClient):
        """Background task for tracking portfolio balance over time."""
        from src.utils.database import BalanceSnapshot
        
        while not self.shutdown_event.is_set():
            try:
                # Get current balance
                balance_response = await kalshi_client.get_balance()
                cash_balance = balance_response.get('balance', 0) / 100  # Convert cents to dollars
                
                # Get positions and calculate position value
                positions_response = await kalshi_client.get_positions()
                positions = positions_response.get('market_positions', [])
                
                position_value = 0.0
                unrealized_pnl = 0.0
                open_positions = 0
                
                for pos in positions:
                    qty = pos.get('position', 0)
                    if qty != 0:
                        open_positions += 1
                        # Estimate position value (simplified - assumes 50c average if no price data)
                        market_exposure = pos.get('market_exposure', 0) / 100
                        position_value += abs(market_exposure)
                        
                        # Calculate unrealized P&L if cost basis is available
                        realized_pnl = pos.get('realized_pnl', 0) / 100
                        unrealized_pnl += realized_pnl
                
                # Calculate total value
                total_value = cash_balance + position_value
                
                # Create and record snapshot
                snapshot = BalanceSnapshot(
                    timestamp=datetime.now(),
                    cash_balance=cash_balance,
                    position_value=position_value,
                    total_value=total_value,
                    open_positions=open_positions,
                    unrealized_pnl=unrealized_pnl
                )
                
                await db_manager.record_balance_snapshot(snapshot)
                
                self.logger.debug(
                    f"📊 Balance snapshot: ${total_value:.2f} total "
                    f"(${cash_balance:.2f} cash + ${position_value:.2f} positions)"
                )
                
                # Record every 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                self.logger.error(f"Error in balance tracking: {e}")
                await asyncio.sleep(300)

    async def run(self):
        """Main entry point for Beast Mode Bot."""
        if self.dashboard_mode:
            await self.run_dashboard_mode()
        else:
            await self.run_trading_mode()


async def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Beast Mode Trading Bot 🚀 - Advanced Multi-Strategy Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python beast_mode_bot.py              # Paper trading mode
  python beast_mode_bot.py --live       # Live trading mode  
  python beast_mode_bot.py --dashboard  # Live dashboard mode
  python beast_mode_bot.py --live --log-level DEBUG  # Live mode with debug logs

Beast Mode Features:
  • Market Making (40% allocation) - Profit from spreads
  • Directional Trading (50% allocation) - AI predictions with portfolio optimization
  • Arbitrage Detection (10% allocation) - Cross-market opportunities
  • No time restrictions - Trade any deadline with dynamic exits
  • Kelly Criterion portfolio optimization
  • Real-time risk management and rebalancing
  • Cost controls and budget management
        """
    )
    
    parser.add_argument(
        "--live", 
        action="store_true", 
        help="Run in LIVE trading mode (default: paper trading)"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Run in live dashboard mode for monitoring"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level=args.log_level)
    
    # Warn about live mode
    if args.live and not args.dashboard:
        print("⚠️  WARNING: LIVE TRADING MODE ENABLED")
        print("💰 This will use real money and place actual trades!")
        print("🚀 LIVE TRADING MODE CONFIRMED")
    
    # Create and run Beast Mode Bot
    bot = BeastModeBot(live_mode=args.live, dashboard_mode=args.dashboard)
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Beast Mode Bot stopped by user")
    except Exception as e:
        print(f"❌ Beast Mode Bot error: {e}")
        raise 