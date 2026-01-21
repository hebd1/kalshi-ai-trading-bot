"""
Database manager for the Kalshi trading system.
"""

import os
import aiosqlite
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from src.utils.logging_setup import TradingLoggerMixin


@dataclass
class Market:
    """Represents a market in the database."""
    market_id: str
    title: str
    yes_price: float
    no_price: float
    volume: int
    expiration_ts: int
    category: str
    status: str
    last_updated: datetime
    has_position: bool = False

@dataclass
class Position:
    """Represents a trading position."""
    market_id: str
    side: str  # "YES" or "NO"
    entry_price: float
    quantity: int
    timestamp: datetime
    rationale: Optional[str] = None
    confidence: Optional[float] = None
    live: bool = False
    status: str = "open"  # open, closed, pending
    id: Optional[int] = None
    strategy: Optional[str] = None  # Strategy that created this position
    tracked: bool = True  # Whether to track P&L for this position (False for legacy positions)
    
    # Enhanced exit strategy fields
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    max_hold_hours: Optional[int] = None  # Maximum hours to hold position
    target_confidence_change: Optional[float] = None  # Exit if confidence drops by this amount

@dataclass
class TradeLog:
    """Represents a closed trade for logging and analysis."""
    market_id: str
    side: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    entry_timestamp: datetime
    exit_timestamp: datetime
    rationale: str
    strategy: Optional[str] = None  # Strategy that created this trade
    id: Optional[int] = None
    exit_reason: Optional[str] = None  # Explicit exit reason (stop_loss, take_profit, market_resolution, time_based)
    slippage: Optional[float] = None  # Difference between expected and actual fill price


@dataclass
class Order:
    """Represents an order (buy/sell, market/limit)."""
    market_id: str
    side: str  # "YES" or "NO"
    action: str  # "buy" or "sell"
    order_type: str  # "market" or "limit"
    quantity: int
    created_at: datetime
    status: str = "pending"  # pending, placed, filled, cancelled, expired
    price: Optional[float] = None  # Limit price (None for market orders)
    kalshi_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    position_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class BalanceSnapshot:
    """Represents a point-in-time snapshot of portfolio balance."""
    timestamp: datetime
    cash_balance: float
    position_value: float
    total_value: float
    open_positions: int = 0
    unrealized_pnl: float = 0.0
    id: Optional[int] = None


@dataclass
class APILatencyRecord:
    """Represents an API call latency measurement."""
    timestamp: datetime
    endpoint: str
    method: str
    latency_ms: float
    status_code: Optional[int] = None
    success: bool = True
    id: Optional[int] = None


@dataclass
class LLMQuery:
    """Represents an LLM query and response for analysis."""
    timestamp: datetime
    strategy: str  # Which strategy made the query
    query_type: str  # Type of query (market_analysis, movement_prediction, etc.)
    market_id: Optional[str]  # Market being analyzed (if applicable)
    prompt: str  # The prompt sent to LLM
    response: str  # LLM response
    tokens_used: Optional[int] = None  # Tokens consumed
    cost_usd: Optional[float] = None  # Cost in USD
    confidence_extracted: Optional[float] = None  # Confidence if extracted
    decision_extracted: Optional[str] = None  # Decision if extracted
    id: Optional[int] = None


class DatabaseManager(TradingLoggerMixin):
    """Manages database operations for the trading system."""

    def __init__(self, db_path: str = None):
        """Initialize database connection.
        
        Args:
            db_path: Path to database file. If None, uses DB_PATH env var or defaults to 'trading_system.db'
        """
        if db_path is None:
            # Check environment variable first (for Docker), then use default
            db_path = os.getenv("DB_PATH", "trading_system.db")
        self.db_path = db_path
        self.logger.info("Initializing database manager", db_path=db_path)

    async def initialize(self) -> None:
        """Initialize database schema and run migrations."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._create_tables(db)
            await self._run_migrations(db)
            await db.commit()
        self.logger.info("Database initialized successfully")

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """Run database migrations for schema updates."""
        try:
            # Migration 1: Add strategy column to positions table
            cursor = await db.execute("PRAGMA table_info(positions)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'strategy' not in column_names:
                self.logger.info("Adding strategy column to positions table")
                await db.execute("ALTER TABLE positions ADD COLUMN strategy TEXT")
            
            # Migration 2: Add strategy column to trade_logs table
            cursor = await db.execute("PRAGMA table_info(trade_logs)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'strategy' not in column_names:
                self.logger.info("Adding strategy column to trade_logs table")
                await db.execute("ALTER TABLE trade_logs ADD COLUMN strategy TEXT")
            
            # Migration 3: Add LLM queries table if it doesn't exist
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_queries'")
            table_exists = await cursor.fetchone()
            
            if not table_exists:
                self.logger.info("Creating llm_queries table")
                await db.execute("""
                    CREATE TABLE llm_queries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        query_type TEXT NOT NULL,
                        market_id TEXT,
                        prompt TEXT NOT NULL,
                        response TEXT NOT NULL,
                        tokens_used INTEGER,
                        cost_usd REAL,
                        confidence_extracted REAL,
                        decision_extracted TEXT
                    )
                """)
                
                            # Migration 4: Update existing positions with strategy based on rationale
            await self._migrate_existing_strategy_data(db)
            
        except Exception as e:
            self.logger.error(f"Error running migrations: {e}")

    async def _migrate_existing_strategy_data(self, db: aiosqlite.Connection) -> None:
        """Migrate existing position data to include strategy information."""
        try:
            # Update positions based on rationale patterns
            await db.execute("""
                UPDATE positions 
                SET strategy = 'quick_flip_scalping' 
                WHERE strategy IS NULL AND rationale LIKE 'QUICK FLIP:%'
            """)
            
            await db.execute("""
                UPDATE positions 
                SET strategy = 'portfolio_optimization' 
                WHERE strategy IS NULL AND rationale LIKE 'Portfolio optimization allocation:%'
            """)
            
            await db.execute("""
                UPDATE positions 
                SET strategy = 'market_making' 
                WHERE strategy IS NULL AND (
                    rationale LIKE '%market making%' OR 
                    rationale LIKE '%spread profit%'
                )
            """)
            
            await db.execute("""
                UPDATE positions 
                SET strategy = 'directional_trading' 
                WHERE strategy IS NULL AND (
                    rationale LIKE 'High-confidence%' OR
                    rationale LIKE '%near-expiry%' OR
                    rationale LIKE '%decision%'
                )
            """)
            
            # Update trade_logs similarly
            await db.execute("""
                UPDATE trade_logs 
                SET strategy = 'quick_flip_scalping' 
                WHERE strategy IS NULL AND rationale LIKE 'QUICK FLIP:%'
            """)
            
            await db.execute("""
                UPDATE trade_logs 
                SET strategy = 'portfolio_optimization' 
                WHERE strategy IS NULL AND rationale LIKE 'Portfolio optimization allocation:%'
            """)
            
            await db.execute("""
                UPDATE trade_logs 
                SET strategy = 'market_making' 
                WHERE strategy IS NULL AND (
                    rationale LIKE '%market making%' OR 
                    rationale LIKE '%spread profit%'
                )
            """)
            
            await db.execute("""
                UPDATE trade_logs 
                SET strategy = 'directional_trading' 
                WHERE strategy IS NULL AND (
                    rationale LIKE 'High-confidence%' OR
                    rationale LIKE '%near-expiry%' OR
                    rationale LIKE '%decision%'
                )
            """)
            
            self.logger.info("Migrated existing position/trade data with strategy information")
            
        except Exception as e:
            self.logger.error(f"Error migrating existing strategy data: {e}")

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create all database tables."""
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS markets (
                market_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                yes_price REAL NOT NULL,
                no_price REAL NOT NULL,
                volume INTEGER NOT NULL,
                expiration_ts INTEGER NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                has_position BOOLEAN NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                rationale TEXT,
                confidence REAL,
                live BOOLEAN NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',
                strategy TEXT,
                tracked BOOLEAN NOT NULL DEFAULT 1,
                stop_loss_price REAL,
                take_profit_price REAL,
                max_hold_hours INTEGER,
                target_confidence_change REAL,
                UNIQUE(market_id, side)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS trade_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                pnl REAL NOT NULL,
                entry_timestamp TEXT NOT NULL,
                exit_timestamp TEXT NOT NULL,
                rationale TEXT,
                strategy TEXT,
                exit_reason TEXT,
                slippage REAL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                analysis_timestamp TEXT NOT NULL,
                decision_action TEXT NOT NULL,
                confidence REAL,
                cost_usd REAL NOT NULL,
                analysis_type TEXT NOT NULL DEFAULT 'standard'
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_cost_tracking (
                date TEXT PRIMARY KEY,
                total_ai_cost REAL NOT NULL DEFAULT 0.0,
                analysis_count INTEGER NOT NULL DEFAULT 0,
                decision_count INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS llm_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                strategy TEXT NOT NULL,
                query_type TEXT NOT NULL,
                market_id TEXT,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                tokens_used INTEGER,
                cost_usd REAL,
                confidence_extracted REAL,
                decision_extracted TEXT
            )
        """)

        # Add analysis_reports table for performance tracking
        await db.execute("""
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                health_score REAL NOT NULL,
                critical_issues INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                action_items INTEGER DEFAULT 0,
                report_file TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Orders table for tracking all orders (buy/sell, market/limit)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                side TEXT NOT NULL,
                action TEXT NOT NULL,
                order_type TEXT NOT NULL,
                price REAL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                kalshi_order_id TEXT,
                client_order_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                filled_at TEXT,
                fill_price REAL,
                position_id INTEGER,
                FOREIGN KEY (position_id) REFERENCES positions(id)
            )
        """)

        # Balance history table for tracking portfolio value over time
        await db.execute("""
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cash_balance REAL NOT NULL,
                position_value REAL NOT NULL,
                total_value REAL NOT NULL,
                open_positions INTEGER NOT NULL DEFAULT 0,
                unrealized_pnl REAL DEFAULT 0.0
            )
        """)

        # API latency tracking table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_latency (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                status_code INTEGER,
                success BOOLEAN NOT NULL DEFAULT 1
            )
        """)

        # Create indices for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_market_analyses_market_id ON market_analyses(market_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_market_analyses_timestamp ON market_analyses(analysis_timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_cost_date ON daily_cost_tracking(date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_market_id ON orders(market_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp ON balance_history(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_api_latency_timestamp ON api_latency(timestamp)")
        
        # Run migrations to ensure schema is up to date
        await self._run_migrations(db)
        
        self.logger.info("Tables created or already exist.")

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """Run database migrations to ensure schema is up to date."""
        try:
            # Check if positions table has the new columns
            cursor = await db.execute("PRAGMA table_info(positions)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Add missing columns for enhanced exit strategy
            if 'stop_loss_price' not in column_names:
                await db.execute("ALTER TABLE positions ADD COLUMN stop_loss_price REAL")
                self.logger.info("Added stop_loss_price column to positions table")
                
            if 'take_profit_price' not in column_names:
                await db.execute("ALTER TABLE positions ADD COLUMN take_profit_price REAL")
                self.logger.info("Added take_profit_price column to positions table")
                
            if 'max_hold_hours' not in column_names:
                await db.execute("ALTER TABLE positions ADD COLUMN max_hold_hours INTEGER")
                self.logger.info("Added max_hold_hours column to positions table")
                
            if 'target_confidence_change' not in column_names:
                await db.execute("ALTER TABLE positions ADD COLUMN target_confidence_change REAL")
                self.logger.info("Added target_confidence_change column to positions table")
                
            if 'tracked' not in column_names:
                await db.execute("ALTER TABLE positions ADD COLUMN tracked BOOLEAN NOT NULL DEFAULT 1")
                self.logger.info("Added tracked column to positions table")
            
            # Migration: Add exit_reason and slippage columns to trade_logs
            cursor = await db.execute("PRAGMA table_info(trade_logs)")
            trade_log_columns = await cursor.fetchall()
            trade_log_column_names = [col[1] for col in trade_log_columns]
            
            if 'exit_reason' not in trade_log_column_names:
                await db.execute("ALTER TABLE trade_logs ADD COLUMN exit_reason TEXT")
                self.logger.info("Added exit_reason column to trade_logs table")
                
            if 'slippage' not in trade_log_column_names:
                await db.execute("ALTER TABLE trade_logs ADD COLUMN slippage REAL")
                self.logger.info("Added slippage column to trade_logs table")
                
            await db.commit()
            
        except Exception as e:
            self.logger.error(f"Error running migrations: {e}")

    async def upsert_markets(self, markets: List[Market]):
        """
        Upsert a list of markets into the database.
        
        Args:
            markets: A list of Market dataclass objects.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # SQLite STRFTIME arguments needs to be a string
            # and asdict converts datetime to datetime object
            # so we need to convert it to string manually
            market_dicts = []
            for m in markets:
                market_dict = asdict(m)
                market_dict['last_updated'] = m.last_updated.isoformat()
                market_dicts.append(market_dict)

            await db.executemany("""
                INSERT INTO markets (market_id, title, yes_price, no_price, volume, expiration_ts, category, status, last_updated, has_position)
                VALUES (:market_id, :title, :yes_price, :no_price, :volume, :expiration_ts, :category, :status, :last_updated, :has_position)
                ON CONFLICT(market_id) DO UPDATE SET
                    title=excluded.title,
                    yes_price=excluded.yes_price,
                    no_price=excluded.no_price,
                    volume=excluded.volume,
                    expiration_ts=excluded.expiration_ts,
                    category=excluded.category,
                    status=excluded.status,
                    last_updated=excluded.last_updated,
                    has_position=excluded.has_position
            """, market_dicts)
            await db.commit()
            self.logger.info(f"Upserted {len(markets)} markets.")

    async def get_eligible_markets(self, volume_min: int, max_days_to_expiry: int) -> List[Market]:
        """
        Get markets that are eligible for trading.

        Args:
            volume_min: Minimum trading volume.
            max_days_to_expiry: Maximum days to expiration.
        
        Returns:
            A list of eligible markets.
        """
        now_ts = int(datetime.now().timestamp())
        max_expiry_ts = now_ts + (max_days_to_expiry * 24 * 60 * 60)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM markets
                WHERE
                    volume >= ? AND
                    expiration_ts > ? AND
                    expiration_ts <= ? AND
                    status = 'active' AND
                    has_position = 0
            """, (volume_min, now_ts, max_expiry_ts))
            rows = await cursor.fetchall()
            
            markets = []
            for row in rows:
                market_dict = dict(row)
                market_dict['last_updated'] = datetime.fromisoformat(market_dict['last_updated'])
                markets.append(Market(**market_dict))
            return markets

    async def get_markets_with_positions(self) -> set[str]:
        """
        Returns a set of market IDs that have associated open positions.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT DISTINCT market_id FROM positions WHERE status IN ('open', 'pending')
            """)
            rows = await cursor.fetchall()
            return {row[0] for row in rows}

    async def is_position_opening_for_market(self, market_id: str) -> bool:
        """
        Checks if a position is currently being opened for a given market.
        This is to prevent race conditions where multiple workers try to open a position for the same market.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT market_id FROM positions WHERE market_id = ? AND status = 'pending' LIMIT 1
            """, (market_id,))
            row = await cursor.fetchone()
            return row is not None

    async def get_open_non_live_positions(self) -> List[Position]:
        """
        Get all positions that are open and not live.
        
        Returns:
            A list of Position objects.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions WHERE status = 'open' AND live = 0")
            rows = await cursor.fetchall()
            
            positions = []
            for row in rows:
                position_dict = dict(row)
                position_dict['timestamp'] = datetime.fromisoformat(position_dict['timestamp'])
                positions.append(Position(**position_dict))
            return positions

    async def get_open_live_positions(self) -> List[Position]:
        """
        Get all positions that are open and live.
        
        Returns:
            A list of Position objects.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions WHERE status = 'open' AND live = 1")
            rows = await cursor.fetchall()
            
            positions = []
            for row in rows:
                position_dict = dict(row)
                position_dict['timestamp'] = datetime.fromisoformat(position_dict['timestamp'])
                positions.append(Position(**position_dict))
            return positions

    async def update_position_status(self, position_id: int, status: str):
        """
        Updates the status of a position.

        Args:
            position_id: The id of the position to update.
            status: The new status ('closed', 'voided').
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE positions SET status = ? WHERE id = ?
            """, (status, position_id))
            await db.commit()
            self.logger.info(f"Updated position {position_id} status to {status}.")

    async def get_position_by_market_id(self, market_id: str) -> Optional[Position]:
        """
        Get a position by market ID.
        
        Args:
            market_id: The ID of the market.
            
        Returns:
            A Position object if found, otherwise None.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions WHERE market_id = ? AND status = 'open' LIMIT 1", (market_id,))
            row = await cursor.fetchone()
            if row:
                position_dict = dict(row)
                position_dict['timestamp'] = datetime.fromisoformat(position_dict['timestamp'])
                return Position(**position_dict)
            return None

    async def get_position_by_market_and_side(self, market_id: str, side: str) -> Optional[Position]:
        """
        Get a position by market ID and side.
        
        Args:
            market_id: The ID of the market.
            side: The side of the position ('YES' or 'NO').

        Returns:
            A Position object if found, otherwise None.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM positions WHERE market_id = ? AND side = ? AND status = 'open'", 
                (market_id, side)
            )
            row = await cursor.fetchone()
            if row:
                position_dict = dict(row)
                position_dict['timestamp'] = datetime.fromisoformat(position_dict['timestamp'])
                return Position(**position_dict)
            return None

    async def add_trade_log(self, trade_log: TradeLog) -> None:
        """
        Add a trade log entry with duplicate prevention.
        
        Args:
            trade_log: The trade log to add.
        """
        trade_dict = asdict(trade_log)
        trade_dict['entry_timestamp'] = trade_log.entry_timestamp.isoformat()
        trade_dict['exit_timestamp'] = trade_log.exit_timestamp.isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Check for duplicate trade log entries to prevent phantom entries
            # A duplicate is defined as same market_id, side, exit_timestamp (within 1 minute)
            cursor = await db.execute("""
                SELECT COUNT(*) FROM trade_logs 
                WHERE market_id = ? 
                AND side = ? 
                AND ABS(CAST((julianday(exit_timestamp) - julianday(?)) * 24 * 60 AS INTEGER)) < 1
            """, (trade_log.market_id, trade_log.side, trade_dict['exit_timestamp']))
            count = (await cursor.fetchone())[0]
            
            if count > 0:
                self.logger.warning(
                    f"Duplicate trade log detected for {trade_log.market_id} {trade_log.side}, skipping insert",
                    exit_timestamp=trade_dict['exit_timestamp']
                )
                return
            
            await db.execute("""
                INSERT INTO trade_logs (
                    market_id, side, entry_price, exit_price, quantity, pnl, 
                    entry_timestamp, exit_timestamp, rationale, strategy, 
                    exit_reason, slippage
                )
                VALUES (
                    :market_id, :side, :entry_price, :exit_price, :quantity, :pnl, 
                    :entry_timestamp, :exit_timestamp, :rationale, :strategy,
                    :exit_reason, :slippage
                )
            """, trade_dict)
            await db.commit()
            self.logger.info(
                f"Added trade log for market {trade_log.market_id}",
                pnl=trade_log.pnl,
                exit_reason=trade_log.exit_reason
            )

    async def get_performance_by_strategy(self) -> Dict[str, Dict]:
        """
        Get performance metrics broken down by strategy.
        
        Returns:
            Dictionary with strategy names as keys and performance metrics as values.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if strategy column exists in trade_logs
            cursor = await db.execute("PRAGMA table_info(trade_logs)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            has_strategy_in_trades = 'strategy' in column_names
            
            completed_stats = []
            
            if has_strategy_in_trades:
                # Get stats from completed trades (trade_logs)
                cursor = await db.execute("""
                    SELECT 
                        strategy,
                        COUNT(*) as trade_count,
                        SUM(pnl) as total_pnl,
                        AVG(pnl) as avg_pnl,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losing_trades,
                        MAX(pnl) as best_trade,
                        MIN(pnl) as worst_trade
                    FROM trade_logs 
                    WHERE strategy IS NOT NULL
                    GROUP BY strategy
                """)
                completed_stats = await cursor.fetchall()
            else:
                # If no strategy column, create a generic entry
                cursor = await db.execute("""
                    SELECT 
                        'legacy_trades' as strategy,
                        COUNT(*) as trade_count,
                        SUM(pnl) as total_pnl,
                        AVG(pnl) as avg_pnl,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losing_trades,
                        MAX(pnl) as best_trade,
                        MIN(pnl) as worst_trade
                    FROM trade_logs
                """)
                result = await cursor.fetchone()
                if result and result['trade_count'] > 0:
                    completed_stats = [result]
            
            # Check if strategy column exists in positions
            cursor = await db.execute("PRAGMA table_info(positions)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            has_strategy_in_positions = 'strategy' in column_names
            
            open_stats = []
            
            if has_strategy_in_positions:
                # Get current open positions by strategy
                cursor = await db.execute("""
                    SELECT 
                        strategy,
                        COUNT(*) as open_positions,
                        SUM(quantity * entry_price) as capital_deployed
                    FROM positions 
                    WHERE status = 'open' AND strategy IS NOT NULL
                    GROUP BY strategy
                """)
                open_stats = await cursor.fetchall()
            else:
                # If no strategy column, create a generic entry
                cursor = await db.execute("""
                    SELECT 
                        'legacy_positions' as strategy,
                        COUNT(*) as open_positions,
                        SUM(quantity * entry_price) as capital_deployed
                    FROM positions 
                    WHERE status = 'open'
                """)
                result = await cursor.fetchone()
                if result and result['open_positions'] > 0:
                    open_stats = [result]
            
            # Combine the results
            performance = {}
            
            # Add completed trade stats
            for row in completed_stats:
                strategy = row['strategy'] or 'unknown'
                win_rate = (row['winning_trades'] / row['trade_count']) * 100 if row['trade_count'] > 0 else 0
                
                performance[strategy] = {
                    'completed_trades': row['trade_count'],
                    'total_pnl': row['total_pnl'],
                    'avg_pnl_per_trade': row['avg_pnl'],
                    'win_rate_pct': win_rate,
                    'winning_trades': row['winning_trades'],
                    'losing_trades': row['losing_trades'],
                    'best_trade': row['best_trade'],
                    'worst_trade': row['worst_trade'],
                    'open_positions': 0,
                    'capital_deployed': 0.0
                }
            
            # Add open position stats
            for row in open_stats:
                strategy = row['strategy'] or 'unknown'
                if strategy not in performance:
                    performance[strategy] = {
                        'completed_trades': 0,
                        'total_pnl': 0.0,
                        'avg_pnl_per_trade': 0.0,
                        'win_rate_pct': 0.0,
                        'winning_trades': 0,
                        'losing_trades': 0,
                        'best_trade': 0.0,
                        'worst_trade': 0.0,
                        'open_positions': 0,
                        'capital_deployed': 0.0
                    }
                
                performance[strategy]['open_positions'] = row['open_positions']
                performance[strategy]['capital_deployed'] = row['capital_deployed']
            
            return performance

    async def log_llm_query(self, llm_query: LLMQuery) -> None:
        """Log an LLM query and response for analysis."""
        try:
            query_dict = asdict(llm_query)
            query_dict['timestamp'] = llm_query.timestamp.isoformat()
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO llm_queries (
                        timestamp, strategy, query_type, market_id, prompt, response,
                        tokens_used, cost_usd, confidence_extracted, decision_extracted
                    ) VALUES (
                        :timestamp, :strategy, :query_type, :market_id, :prompt, :response,
                        :tokens_used, :cost_usd, :confidence_extracted, :decision_extracted
                    )
                """, query_dict)
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error logging LLM query: {e}")

    async def get_llm_queries(
        self, 
        strategy: Optional[str] = None,
        hours_back: int = 24,
        limit: int = 100
    ) -> List[LLMQuery]:
        """Get recent LLM queries, optionally filtered by strategy."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Check if llm_queries table exists
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_queries'")
                table_exists = await cursor.fetchone()
                
                if not table_exists:
                    self.logger.info("LLM queries table doesn't exist yet - will be created on first query")
                    return []
                
                if strategy:
                    cursor = await db.execute("""
                        SELECT * FROM llm_queries 
                        WHERE strategy = ? AND timestamp >= ?
                        ORDER BY timestamp DESC LIMIT ?
                    """, (strategy, cutoff_time.isoformat(), limit))
                else:
                    cursor = await db.execute("""
                        SELECT * FROM llm_queries 
                        WHERE timestamp >= ?
                        ORDER BY timestamp DESC LIMIT ?
                    """, (cutoff_time.isoformat(), limit))
                
                rows = await cursor.fetchall()
                
                queries = []
                for row in rows:
                    query_dict = dict(row)
                    query_dict['timestamp'] = datetime.fromisoformat(query_dict['timestamp'])
                    queries.append(LLMQuery(**query_dict))
                
                return queries
                
        except Exception as e:
            self.logger.error(f"Error getting LLM queries: {e}")
            return []

    async def get_llm_stats_by_strategy(self) -> Dict[str, Dict]:
        """Get LLM usage statistics by strategy."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Check if llm_queries table exists
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_queries'")
                table_exists = await cursor.fetchone()
                
                if not table_exists:
                    self.logger.info("LLM queries table doesn't exist yet - will be created on first query")
                    return {}
                
                cursor = await db.execute("""
                    SELECT 
                        strategy,
                        COUNT(*) as query_count,
                        SUM(tokens_used) as total_tokens,
                        SUM(cost_usd) as total_cost,
                        AVG(confidence_extracted) as avg_confidence,
                        MIN(timestamp) as first_query,
                        MAX(timestamp) as last_query
                    FROM llm_queries 
                    WHERE timestamp >= datetime('now', '-7 days')
                    GROUP BY strategy
                """)
                
                rows = await cursor.fetchall()
                
                stats = {}
                for row in rows:
                    stats[row['strategy']] = {
                        'query_count': row['query_count'],
                        'total_tokens': row['total_tokens'] or 0,
                        'total_cost': row['total_cost'] or 0.0,
                        'avg_confidence': row['avg_confidence'] or 0.0,
                        'first_query': row['first_query'],
                        'last_query': row['last_query']
                    }
                
                return stats
                
        except Exception as e:
            self.logger.error(f"Error getting LLM stats: {e}")
            return {}

    async def close(self):
        """Close database connections (no-op for aiosqlite)."""
        # aiosqlite doesn't require explicit closing of connections
        # since we use context managers, but we provide this method
        # for compatibility with other code that expects it
        pass

    async def record_market_analysis(
        self, 
        market_id: str, 
        decision_action: str, 
        confidence: float, 
        cost_usd: float,
        analysis_type: str = 'standard'
    ) -> None:
        """Record that a market was analyzed to prevent duplicate analysis."""
        now = datetime.now().isoformat()
        today = datetime.now().strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(self.db_path) as db:
            # Record the analysis
            await db.execute("""
                INSERT INTO market_analyses (market_id, analysis_timestamp, decision_action, confidence, cost_usd, analysis_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (market_id, now, decision_action, confidence, cost_usd, analysis_type))
            
            # Update daily cost tracking
            await db.execute("""
                INSERT INTO daily_cost_tracking (date, total_ai_cost, analysis_count, decision_count)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_ai_cost = total_ai_cost + excluded.total_ai_cost,
                    analysis_count = analysis_count + 1,
                    decision_count = decision_count + excluded.decision_count
            """, (today, cost_usd, 1 if decision_action != 'SKIP' else 0))
            
            await db.commit()

    async def was_recently_analyzed(self, market_id: str, hours: int = 6) -> bool:
        """Check if market was analyzed within the specified hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff_time.isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT COUNT(*) FROM market_analyses 
                WHERE market_id = ? AND analysis_timestamp > ?
            """, (market_id, cutoff_str))
            count = (await cursor.fetchone())[0]
            return count > 0

    async def get_daily_ai_cost(self, date: str = None) -> float:
        """Get total AI cost for a specific date (defaults to today)."""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT total_ai_cost FROM daily_cost_tracking WHERE date = ?
            """, (date,))
            row = await cursor.fetchone()
            return row[0] if row else 0.0

    async def get_market_analysis_count_today(self, market_id: str) -> int:
        """Get number of times market was analyzed today."""
        today = datetime.now().strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT COUNT(*) FROM market_analyses 
                WHERE market_id = ? AND DATE(analysis_timestamp) = ?
            """, (market_id, today))
            count = (await cursor.fetchone())[0]
            return count

    async def get_all_trade_logs(self) -> List[TradeLog]:
        """
        Get all trade logs from the database.
        
        Returns:
            A list of TradeLog objects.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM trade_logs")
            rows = await cursor.fetchall()
            
            logs = []
            for row in rows:
                log_dict = dict(row)
                log_dict['entry_timestamp'] = datetime.fromisoformat(log_dict['entry_timestamp'])
                log_dict['exit_timestamp'] = datetime.fromisoformat(log_dict['exit_timestamp'])
                logs.append(TradeLog(**log_dict))
            return logs

    async def update_position_to_live(self, position_id: int, entry_price: float):
        """
        Updates the status and entry price of a position after it has been executed.

        Args:
            position_id: The ID of the position to update.
            entry_price: The actual entry price from the exchange.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE positions 
                SET live = 1, entry_price = ?
                WHERE id = ?
            """, (entry_price, position_id))
            await db.commit()
        self.logger.info(f"Updated position {position_id} to live.")

    async def add_position(self, position: Position) -> Optional[int]:
        """
        Adds a new position to the database, if one doesn't already exist for the same market and side.
        
        Args:
            position: The position to add.
        
        Returns:
            The ID of the newly inserted position, or None if a position already exists.
        """
        existing_position = await self.get_position_by_market_and_side(position.market_id, position.side)
        if existing_position:
            self.logger.warning(f"Position already exists for market {position.market_id} and side {position.side}.")
            return None

        async with aiosqlite.connect(self.db_path) as db:
            position_dict = asdict(position)
            # aiosqlite does not support dataclasses with datetime objects
            position_dict['timestamp'] = position.timestamp.isoformat()

            cursor = await db.execute("""
                INSERT INTO positions (market_id, side, entry_price, quantity, timestamp, rationale, confidence, live, status, strategy, tracked, stop_loss_price, take_profit_price, max_hold_hours, target_confidence_change)
                VALUES (:market_id, :side, :entry_price, :quantity, :timestamp, :rationale, :confidence, :live, :status, :strategy, :tracked, :stop_loss_price, :take_profit_price, :max_hold_hours, :target_confidence_change)
            """, position_dict)
            await db.commit()
            
            # Set has_position to True for the market
            await db.execute("UPDATE markets SET has_position = 1 WHERE market_id = ?", (position.market_id,))
            await db.commit()

            self.logger.info(f"Added position for market {position.market_id}", position_id=cursor.lastrowid)
            return cursor.lastrowid

    async def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM positions WHERE status = 'open'"
            )
            rows = await cursor.fetchall()
            
            positions = []
            for row in rows:
                # Convert database row to Position object
                # Column mapping (from PRAGMA table_info):
                # 0=id, 1=market_id, 2=side, 3=entry_price, 4=quantity, 5=timestamp,
                # 6=rationale, 7=confidence, 8=live, 9=status, 10=strategy,
                # 11=stop_loss_price, 12=take_profit_price, 13=max_hold_hours,
                # 14=target_confidence_change, 15=tracked
                position = Position(
                    market_id=row[1],
                    side=row[2],
                    entry_price=row[3],
                    quantity=row[4],
                    timestamp=datetime.fromisoformat(row[5]),
                    rationale=row[6],
                    confidence=row[7],
                    live=bool(row[8]),
                    status=row[9],
                    id=row[0],
                    strategy=row[10],
                    tracked=bool(row[15]) if row[15] is not None else True,
                    stop_loss_price=row[11],
                    take_profit_price=row[12],
                    max_hold_hours=row[13],
                    target_confidence_change=row[14]
                )
                positions.append(position)
            
            return positions

    # ==================== ORDER TRACKING METHODS ====================

    async def add_order(self, order: Order) -> Optional[int]:
        """
        Add a new order to the database.
        
        Args:
            order: The order to add.
        
        Returns:
            The ID of the newly inserted order, or None on failure.
        """
        try:
            order_dict = asdict(order)
            order_dict['created_at'] = order.created_at.isoformat()
            if order.updated_at:
                order_dict['updated_at'] = order.updated_at.isoformat()
            if order.filled_at:
                order_dict['filled_at'] = order.filled_at.isoformat()
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO orders (
                        market_id, side, action, order_type, price, quantity, status,
                        kalshi_order_id, client_order_id, created_at, updated_at,
                        filled_at, fill_price, position_id
                    ) VALUES (
                        :market_id, :side, :action, :order_type, :price, :quantity, :status,
                        :kalshi_order_id, :client_order_id, :created_at, :updated_at,
                        :filled_at, :fill_price, :position_id
                    )
                """, order_dict)
                await db.commit()
                
                self.logger.info(
                    f"Added order for market {order.market_id}",
                    order_id=cursor.lastrowid,
                    action=order.action,
                    order_type=order.order_type
                )
                return cursor.lastrowid
                
        except Exception as e:
            self.logger.error(f"Error adding order: {e}")
            return None

    async def update_order_status(
        self, 
        order_id: int, 
        status: str, 
        kalshi_order_id: Optional[str] = None,
        fill_price: Optional[float] = None
    ) -> None:
        """Update the status of an order."""
        now = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            if status == 'filled' and fill_price:
                await db.execute("""
                    UPDATE orders 
                    SET status = ?, updated_at = ?, filled_at = ?, fill_price = ?, kalshi_order_id = COALESCE(?, kalshi_order_id)
                    WHERE id = ?
                """, (status, now, now, fill_price, kalshi_order_id, order_id))
            else:
                await db.execute("""
                    UPDATE orders 
                    SET status = ?, updated_at = ?, kalshi_order_id = COALESCE(?, kalshi_order_id)
                    WHERE id = ?
                """, (status, now, kalshi_order_id, order_id))
            await db.commit()
            
        self.logger.info(f"Updated order {order_id} status to {status}")

    async def get_pending_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """Get all pending orders, optionally filtered by market."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if market_id:
                cursor = await db.execute(
                    "SELECT * FROM orders WHERE status IN ('pending', 'placed') AND market_id = ?",
                    (market_id,)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM orders WHERE status IN ('pending', 'placed')"
                )
            
            rows = await cursor.fetchall()
            
            orders = []
            for row in rows:
                order_dict = dict(row)
                order_dict['created_at'] = datetime.fromisoformat(order_dict['created_at'])
                if order_dict['updated_at']:
                    order_dict['updated_at'] = datetime.fromisoformat(order_dict['updated_at'])
                if order_dict['filled_at']:
                    order_dict['filled_at'] = datetime.fromisoformat(order_dict['filled_at'])
                orders.append(Order(**order_dict))
            
            return orders

    async def get_orders_by_position(self, position_id: int) -> List[Order]:
        """Get all orders for a specific position."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM orders WHERE position_id = ? ORDER BY created_at DESC",
                (position_id,)
            )
            rows = await cursor.fetchall()
            
            orders = []
            for row in rows:
                order_dict = dict(row)
                order_dict['created_at'] = datetime.fromisoformat(order_dict['created_at'])
                if order_dict['updated_at']:
                    order_dict['updated_at'] = datetime.fromisoformat(order_dict['updated_at'])
                if order_dict['filled_at']:
                    order_dict['filled_at'] = datetime.fromisoformat(order_dict['filled_at'])
                orders.append(Order(**order_dict))
            
            return orders

    # ==================== BALANCE HISTORY METHODS ====================

    async def record_balance_snapshot(self, snapshot: BalanceSnapshot) -> Optional[int]:
        """
        Record a balance snapshot for historical tracking.
        
        Args:
            snapshot: The balance snapshot to record.
        
        Returns:
            The ID of the inserted record, or None on failure.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO balance_history (
                        timestamp, cash_balance, position_value, total_value,
                        open_positions, unrealized_pnl
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    snapshot.timestamp.isoformat(),
                    snapshot.cash_balance,
                    snapshot.position_value,
                    snapshot.total_value,
                    snapshot.open_positions,
                    snapshot.unrealized_pnl
                ))
                await db.commit()
                
                self.logger.debug(
                    f"Recorded balance snapshot: ${snapshot.total_value:.2f} total"
                )
                return cursor.lastrowid
                
        except Exception as e:
            self.logger.error(f"Error recording balance snapshot: {e}")
            return None

    async def get_balance_history(
        self, 
        hours_back: int = 24,
        limit: int = 1000
    ) -> List[BalanceSnapshot]:
        """Get balance history for the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM balance_history 
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (cutoff_time.isoformat(), limit))
            
            rows = await cursor.fetchall()
            
            snapshots = []
            for row in rows:
                snapshot_dict = dict(row)
                snapshot_dict['timestamp'] = datetime.fromisoformat(snapshot_dict['timestamp'])
                snapshots.append(BalanceSnapshot(**snapshot_dict))
            
            return snapshots

    async def get_latest_balance(self) -> Optional[BalanceSnapshot]:
        """Get the most recent balance snapshot."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM balance_history ORDER BY timestamp DESC LIMIT 1
            """)
            row = await cursor.fetchone()
            
            if row:
                snapshot_dict = dict(row)
                snapshot_dict['timestamp'] = datetime.fromisoformat(snapshot_dict['timestamp'])
                return BalanceSnapshot(**snapshot_dict)
            return None

    # ==================== API LATENCY TRACKING METHODS ====================

    async def record_api_latency(self, record: APILatencyRecord) -> None:
        """Record an API latency measurement."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO api_latency (
                        timestamp, endpoint, method, latency_ms, status_code, success
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    record.timestamp.isoformat(),
                    record.endpoint,
                    record.method,
                    record.latency_ms,
                    record.status_code,
                    record.success
                ))
                await db.commit()
        except Exception as e:
            # Don't fail the main operation if latency logging fails
            self.logger.debug(f"Failed to record API latency: {e}")

    async def get_api_latency_stats(self, hours_back: int = 24) -> Dict:
        """Get API latency statistics for the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("""
                SELECT 
                    endpoint,
                    COUNT(*) as call_count,
                    AVG(latency_ms) as avg_latency_ms,
                    MIN(latency_ms) as min_latency_ms,
                    MAX(latency_ms) as max_latency_ms,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
                FROM api_latency 
                WHERE timestamp >= ?
                GROUP BY endpoint
                ORDER BY call_count DESC
            """, (cutoff_time.isoformat(),))
            
            rows = await cursor.fetchall()
            
            return {
                row['endpoint']: {
                    'call_count': row['call_count'],
                    'avg_latency_ms': row['avg_latency_ms'],
                    'min_latency_ms': row['min_latency_ms'],
                    'max_latency_ms': row['max_latency_ms'],
                    'failures': row['failures'],
                    'success_rate': (row['call_count'] - row['failures']) / row['call_count'] * 100
                }
                for row in rows
            }