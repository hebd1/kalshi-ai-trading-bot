"""
Unified Advanced Trading System - The Beast Mode 🚀

This system orchestrates all cutting-edge strategies:
1. Market Making Strategy (limit orders for spreads)
2. Advanced Portfolio Optimization (Kelly Criterion Extension)
3. Risk Parity Allocation (equal risk, not equal capital)
4. Dynamic Exit Strategies (time-based, confidence-based, volatility-based)
5. Cross-Market Arbitrage Detection
6. Multi-Model AI Ensemble

The goal: Use ALL available capital optimally across the BEST opportunities
with sophisticated risk management and dynamic rebalancing.

Key innovations:
- No time restrictions (trade any deadline with smart exits)
- Market making for spread profits without directional risk
- Portfolio optimization using latest Kelly Criterion research
- Real-time rebalancing based on market conditions
- Maximum capital utilization through diverse strategies
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

from src.clients.kalshi_client import KalshiClient
from src.clients.xai_client import XAIClient
from src.utils.database import DatabaseManager, Market, Position
from src.config.settings import settings
from src.utils.logging_setup import get_trading_logger

from src.strategies.market_making import (
    AdvancedMarketMaker, 
    MarketMakingOpportunity,
    run_market_making_strategy
)
from src.strategies.portfolio_optimization import (
    AdvancedPortfolioOptimizer, 
    MarketOpportunity, 
    PortfolioAllocation,
    run_portfolio_optimization,
    create_market_opportunities_from_markets
)
from src.strategies.quick_flip_scalping import (
    run_quick_flip_strategy,
    QuickFlipConfig
)
from src.strategies.arbitrage_scanner import ArbitrageScanner


@dataclass
class TradingSystemConfig:
    """Configuration for the unified trading system."""
    # Capital allocation across strategies
    market_making_allocation: float = 0.25  # 25% for market making
    directional_trading_allocation: float = 0.30  # 30% for directional positions
    quick_flip_allocation: float = 0.30     # 30% for quick flip scalping
    arbitrage_allocation: float = 0.15      # 15% for arbitrage opportunities
    
    # Risk management
    max_portfolio_volatility: float = 0.20  # 20% max portfolio vol
    max_correlation_exposure: float = 0.70  # Max 70% in correlated positions
    max_single_position: float = 0.15  # Max 15% in any single position
    
    # Performance targets
    target_sharpe_ratio: float = 2.0
    target_annual_return: float = 0.30  # 30% annual target
    max_drawdown_limit: float = 0.15  # 15% max drawdown
    
    # Rebalancing
    rebalance_frequency_hours: int = 6  # Rebalance every 6 hours
    profit_taking_threshold: float = 0.25  # Take profits at 25%
    loss_cutting_threshold: float = 0.10  # Cut losses at 10%


@dataclass
class TradingSystemResults:
    """Results from unified trading system execution."""
    # Market making results
    market_making_orders: int = 0
    market_making_exposure: float = 0.0
    market_making_expected_profit: float = 0.0
    
    # Directional trading results
    directional_positions: int = 0
    directional_exposure: float = 0.0
    directional_expected_return: float = 0.0
    
    # Portfolio metrics
    total_capital_used: float = 0.0
    portfolio_expected_return: float = 0.0
    portfolio_sharpe_ratio: float = 0.0
    portfolio_volatility: float = 0.0
    
    # Risk metrics
    max_portfolio_drawdown: float = 0.0
    correlation_score: float = 0.0
    diversification_ratio: float = 0.0
    
    # Performance
    total_positions: int = 0
    capital_efficiency: float = 0.0  # % of capital used
    expected_annual_return: float = 0.0


class UnifiedAdvancedTradingSystem:
    """
    The Beast Mode Trading System 🚀
    
    This orchestrates all advanced strategies to maximize returns while
    optimally using ALL available capital with sophisticated risk management.
    
    Strategy allocation:
    1. Market Making (40%): Profit from spreads without directional risk
    2. Directional Trading (50%): Take positions based on AI edge
    3. Arbitrage (10%): Cross-market and temporal arbitrage
    
    Features:
    - No time restrictions (trade any deadline)
    - Dynamic position sizing (Kelly Criterion Extension)
    - Risk parity allocation (equal risk contribution)
    - Real-time rebalancing
    - Multi-strategy diversification
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        kalshi_client: KalshiClient,
        xai_client: XAIClient,
        config: Optional[TradingSystemConfig] = None
    ):
        self.db_manager = db_manager
        self.kalshi_client = kalshi_client
        self.xai_client = xai_client
        self.config = config or TradingSystemConfig()
        self.logger = get_trading_logger("unified_trading_system")
        
        # 🚨 DYNAMIC CAPITAL: Will be set by async_initialize() from actual Kalshi balance
        self.total_capital = 100  # Temporary default, will be updated by async_initialize()
        
        # OLD HARDCODED WAY (REMOVED):
        # self.total_capital = getattr(settings.trading, 'total_capital', 10000)
        self.last_rebalance = datetime.now()
        self.system_metrics = {}
        
        # Capital allocation will be set by async_initialize() after getting actual balance

    async def async_initialize(self):
        """
        Asynchronously initialize the trading system by fetching the current balance
        from Kalshi and setting the total capital.
        """
        try:
            self.logger.info("🔄 Starting async initialization...")
            
            # Get total portfolio value (cash + current positions) with timeout
            self.logger.info("📊 Fetching balance from Kalshi...")
            balance_response = await asyncio.wait_for(
                self.kalshi_client.get_balance(), 
                timeout=30.0
            )
            available_cash = balance_response.get('balance', 0) / 100  # Convert cents to dollars
            self.logger.info(f"✅ Balance fetched: ${available_cash:.2f}")
            
            # Get current positions to calculate total portfolio value
            # NOTE: This includes BOTH tracked and untracked positions for accurate capital allocation
            # Untracked positions (legacy/pre-bot) must be included in risk calculations and position limits
            self.logger.info("📊 Fetching positions from Kalshi...")
            positions_response = await asyncio.wait_for(
                self.kalshi_client.get_positions(),
                timeout=30.0
            )
            positions = positions_response.get('positions', []) if isinstance(positions_response, dict) else []
            self.logger.info(f"✅ Positions fetched: {len(positions)} positions")
            total_position_value = 0
            
            if positions:
                for position in positions:
                    if not isinstance(position, dict):
                        continue  # Skip non-dict positions
                    quantity = position.get('quantity', 0)
                    # SIMPLIFIED: Use 50¢ estimate instead of fetching market data for each position
                    # This prevents initialization hangs from excessive API calls
                    market_id = position.get('market_id')
                    if market_id and quantity != 0:
                        # Use conservative 50¢ estimate for position value during initialization
                        # Actual values will be calculated during tracking
                        total_position_value += abs(quantity) * 0.50
            
            # Total portfolio value is the basis for all allocations
            total_portfolio_value = available_cash + total_position_value
            self.total_capital = total_portfolio_value
            
            self.logger.info(f"💰 PORTFOLIO VALUE: Cash=${available_cash:.2f} + Positions=${total_position_value:.2f} = Total=${self.total_capital:.2f}")
            
            if self.total_capital < 10:  # Minimum $10 to trade
                self.logger.warning(f"⚠️ Total capital too low: ${self.total_capital:.2f} - may limit trading")
                
        except Exception as e:
            self.logger.error(f"Failed to get portfolio value, using default: {e}")
            self.total_capital = 100  # Conservative fallback
        
        # Update capital allocation based on actual balance
        self.market_making_capital = self.total_capital * self.config.market_making_allocation
        self.directional_capital = self.total_capital * self.config.directional_trading_allocation
        self.quick_flip_capital = self.total_capital * self.config.quick_flip_allocation
        self.arbitrage_capital = self.total_capital * self.config.arbitrage_allocation
        
        # Initialize strategy modules with actual capital
        self.market_maker = AdvancedMarketMaker(self.db_manager, self.kalshi_client, self.xai_client)
        self.portfolio_optimizer = AdvancedPortfolioOptimizer(self.db_manager, self.kalshi_client, self.xai_client)
        # Use 1% fee estimate for conservative arbitrage calculation to ensure net profit
        self.arbitrage_scanner = ArbitrageScanner(self.kalshi_client, self.db_manager, fee_pct=0.01)
        
        self.logger.info(f"🎯 CAPITAL ALLOCATION: Market Making=${self.market_making_capital:.2f}, Directional=${self.directional_capital:.2f}, Quick Flip=${self.quick_flip_capital:.2f}, Arbitrage=${self.arbitrage_capital:.2f}")

    async def execute_unified_trading_strategy(self) -> TradingSystemResults:
        """
        Execute the unified trading strategy across all approaches.
        
        Process:
        1. Analyze all available markets (no time restrictions!)
        2. Identify market making opportunities
        3. Identify directional trading opportunities  
        4. Optimize portfolio allocation using advanced Kelly Criterion
        5. Execute trades across all strategies
        6. Monitor and rebalance as needed
        """
        self.logger.info("🚀 Executing Unified Advanced Trading Strategy")
        
        try:
            # Step 0: Check and enforce position limits AND cash reserves
            from src.utils.position_limits import PositionLimitsManager
            from src.utils.cash_reserves import CashReservesManager, is_cash_emergency
            
            limits_manager = PositionLimitsManager(self.db_manager, self.kalshi_client)
            cash_manager = CashReservesManager(self.db_manager, self.kalshi_client)
            
            # Check position limits
            limits_status = await limits_manager.get_position_limits_status()
            self.logger.info(f"📊 POSITION LIMITS STATUS: {limits_status['status']} ({limits_status['position_utilization']})")
            
            # Check cash reserves
            cash_status = await cash_manager.get_cash_status()
            self.logger.info(f"💰 CASH RESERVES STATUS: {cash_status['status']} ({cash_status['reserve_percentage']:.1f}%)")
            
            # Handle cash emergency first (higher priority)
            if cash_status['emergency_status']:
                self.logger.warning(f"🚨 CASH EMERGENCY: {cash_status['recommendations']}")
                emergency_action = await cash_manager.handle_cash_emergency()
                if emergency_action.action_type == 'halt_trading':
                    self.logger.critical(f"🛑 TRADING HALTED DUE TO CASH EMERGENCY: {emergency_action.reason}")
                    return TradingSystemResults()  # Return empty results
                elif emergency_action.action_type == 'close_positions':
                    self.logger.warning(f"⚠️ Need to close {emergency_action.positions_to_close} positions for cash reserves")
            
            # Enforce position limits if needed (after cash check)
            if limits_status['status'] in ['OVER_LIMIT', 'WARNING']:
                self.logger.info(f"⚠️  Position limits enforcement needed: {limits_status['recommendations']}")
                enforcement_result = await limits_manager.enforce_position_limits()
                if enforcement_result['action'] == 'positions_closed':
                    self.logger.info(f"✅ CLOSED {enforcement_result['positions_closed']} positions to meet limits")
            
            # Step 1: Get ALL available markets (no time restrictions) - MORE PERMISSIVE VOLUME
            markets = await self.db_manager.get_eligible_markets(
            volume_min=settings.trading.min_volume,  # Use settings instead of hardcoded 200
            max_days_to_expiry=365  # Accept any timeline with dynamic exits
        )
            if not markets:
                self.logger.warning("No markets available for trading")
                return TradingSystemResults()
            
            self.logger.info(f"Analyzing {len(markets)} markets across all strategies")
            
            # Step 2: Parallel strategy analysis
            market_making_results, portfolio_allocation, quick_flip_results = await asyncio.gather(
                self._execute_market_making_strategy(markets),
                self._execute_directional_trading_strategy(markets),
                self._execute_quick_flip_strategy(markets)
            )
            
            # Step 3: Execute arbitrage opportunities
            arbitrage_results = await self._execute_arbitrage_strategy(markets)
            
            # Step 4: Compile results
            results = self._compile_unified_results(
                market_making_results, portfolio_allocation, quick_flip_results, arbitrage_results
            )
            
            # Step 4.5: Log if no positions were created (removed emergency fallback)
            if results.total_positions == 0:
                self.logger.warning("No positions created by main strategies - investigating why")
            
            # Step 5: Risk management and rebalancing
            await self._manage_risk_and_rebalance(results)
            
            self.logger.info(
                f"🎯 Unified Strategy Complete: "
                f"Capital Used: ${results.total_capital_used:.0f} ({results.capital_efficiency:.1%}), "
                f"Expected Return: {results.expected_annual_return:.1%}, "
                f"Sharpe Ratio: {results.portfolio_sharpe_ratio:.2f}, "
                f"Positions: {results.total_positions}"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in unified trading strategy: {e}")
            return TradingSystemResults()

    async def _execute_market_making_strategy(self, markets: List[Market]) -> Dict:
        """
        Execute market making strategy for spread profits.
        """
        try:
            self.logger.info(f"🎯 Executing Market Making Strategy on {len(markets)} markets")
            
            # Analyze market making opportunities
            opportunities = await self.market_maker.analyze_market_making_opportunities(markets)
            
            if not opportunities:
                self.logger.warning("No market making opportunities found")
                return {'orders_placed': 0, 'expected_profit': 0.0}
            
            # Filter to top opportunities within capital allocation
            max_opportunities = int(self.market_making_capital / 100)  # $100 per opportunity
            top_opportunities = opportunities[:max_opportunities]
            
            # Execute market making
            results = await self.market_maker.execute_market_making_strategy(top_opportunities)
            
            self.logger.info(
                f"✅ Market Making: {results['orders_placed']} orders, "
                f"${results['expected_profit']:.2f} expected profit"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in market making strategy: {e}")
            return {'orders_placed': 0, 'expected_profit': 0.0}

    async def _execute_directional_trading_strategy(self, markets: List[Market]) -> PortfolioAllocation:
        """
        Execute directional trading with advanced portfolio optimization.
        """
        try:
            self.logger.info(f"🎯 Executing Directional Trading Strategy")
            
            # Convert markets to opportunities (with immediate trading capability)
            opportunities = await create_market_opportunities_from_markets(
                markets, self.xai_client, self.kalshi_client, 
                self.db_manager, self.directional_capital
            )
            
            if not opportunities:
                self.logger.warning("No directional trading opportunities found")
                return self.portfolio_optimizer._empty_allocation()
            
            # Filter opportunities based on available capital
            # Adjust portfolio optimizer capital
            original_capital = self.portfolio_optimizer.total_capital
            self.portfolio_optimizer.total_capital = self.directional_capital
            
            # Optimize portfolio
            allocation = await self.portfolio_optimizer.optimize_portfolio(opportunities)
            
            # Restore original capital setting
            self.portfolio_optimizer.total_capital = original_capital
            
            # DEBUG: Log allocation details before execution attempt
            self.logger.info(f"Portfolio allocation result: {len(allocation.allocations) if allocation else 0} allocations, ${allocation.total_capital_used if allocation else 0:.0f} capital used")
            
            # Actually execute the trades from the allocation
            if allocation and allocation.allocations:
                self.logger.info(f"Attempting to execute {len(allocation.allocations)} allocations: {list(allocation.allocations.keys())}")
                execution_results = await self._execute_portfolio_allocations(allocation, opportunities)
                self.logger.info(f"Executed {execution_results['positions_created']} positions from portfolio allocation")
            else:
                self.logger.warning(f"No allocations to execute. Allocation exists: {allocation is not None}, Has allocations: {bool(allocation and allocation.allocations)}")
            
            self.logger.info(
                f"✅ Directional Trading: {len(allocation.allocations)} positions, "
                f"${allocation.total_capital_used:.0f} allocated, "
                f"Sharpe: {allocation.portfolio_sharpe:.2f}"
            )
            
            return allocation
            
        except Exception as e:
            self.logger.error(f"Error in directional trading strategy: {e}")
            return self.portfolio_optimizer._empty_allocation()

    async def _execute_quick_flip_strategy(self, markets: List[Market]) -> Dict:
        """
        Execute quick flip scalping strategy for rapid profits.
        """
        try:
            self.logger.info(f"🎯 Executing Quick Flip Scalping Strategy")
            
            # Configure quick flip strategy for our capital allocation
            quick_flip_config = QuickFlipConfig(
                min_entry_price=1,      # Start with 1¢ opportunities
                max_entry_price=15,     # Up to 15¢ entries
                min_profit_margin=1.0,  # 100% minimum return (1¢ → 2¢)
                max_position_size=100,  # Max 100 contracts per position
                max_concurrent_positions=min(25, int(self.quick_flip_capital / 20)),  # Scale with capital
                capital_per_trade=min(50.0, self.quick_flip_capital / 10),  # Spread risk
                confidence_threshold=0.6,  # 60% minimum confidence
                max_hold_minutes=30     # Quick exit if not filled
            )
            
            # Execute quick flip strategy
            results = await run_quick_flip_strategy(
                db_manager=self.db_manager,
                kalshi_client=self.kalshi_client,
                xai_client=self.xai_client,
                available_capital=self.quick_flip_capital,
                config=quick_flip_config
            )
            
            if 'error' in results:
                self.logger.warning(f"Quick flip strategy error: {results['error']}")
                return {'positions_created': 0, 'sell_orders_placed': 0, 'total_capital_used': 0.0}
            
            self.logger.info(
                f"✅ Quick Flip: {results.get('positions_created', 0)} positions, "
                f"{results.get('sell_orders_placed', 0)} sell orders, "
                f"${results.get('total_capital_used', 0):.0f} capital used"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in quick flip strategy: {e}")
            return {'positions_created': 0, 'sell_orders_placed': 0, 'total_capital_used': 0.0}

    async def _execute_portfolio_allocations(
        self, 
        allocation: PortfolioAllocation, 
        opportunities: List[MarketOpportunity]
    ) -> Dict:
        """
        Convert portfolio allocations to actual Position objects and execute them.
        """
        results = {
            'positions_created': 0,
            'total_capital_used': 0.0,
            'successful_executions': 0,
            'failed_executions': 0
        }
        
        try:
            from src.jobs.execute import execute_position
            
            for market_id, allocation_fraction in allocation.allocations.items():
                try:
                    # Find the corresponding opportunity first to determine intended side
                    opportunity = next((opp for opp in opportunities if opp.market_id == market_id), None)
                    if not opportunity:
                        self.logger.warning(f"Could not find opportunity for {market_id}")
                        continue
                    
                    # Determine the intended side based on edge direction
                    intended_side = "YES" if opportunity.edge > 0 else "NO"
                    
                    # 🚨 ONLY SKIP if we already have a position on the EXACT same market_id AND side
                    existing_position = await self.db_manager.get_position_by_market_and_side(market_id, intended_side)
                    
                    if existing_position:
                        self.logger.debug(f"⏭️ SKIPPING {market_id} {intended_side} - exact position already exists (likely from immediate trade)")
                        results['positions_created'] += 1  # Count as created since it exists
                        results['total_capital_used'] += allocation_fraction * self.directional_capital
                        continue
                    else:
                        # Check if we have the opposite side (just for logging)
                        opposite_side = "NO" if intended_side == "YES" else "YES"
                        opposite_position = await self.db_manager.get_position_by_market_and_side(market_id, opposite_side)
                        if opposite_position:
                            self.logger.info(f"📊 {market_id} - Adding {intended_side} position (already have {opposite_side})")
                        else:
                            self.logger.info(f"📊 {market_id} - New {intended_side} position")
                    
                    # Calculate initial position size
                    initial_position_value = allocation_fraction * self.directional_capital
                    
                    # Check position limits and adjust if needed
                    from src.utils.position_limits import check_can_add_position
                    
                    can_add_position, limit_reason = await check_can_add_position(
                        initial_position_value, self.db_manager, self.kalshi_client
                    )
                    
                    if not can_add_position:
                        # Instead of blocking, try to find a smaller position size that fits
                        self.logger.info(f"⚠️ Position size ${initial_position_value:.2f} exceeds limits, attempting to reduce...")
                        
                        # Try progressively smaller position sizes
                        for reduction_factor in [0.8, 0.6, 0.4, 0.2, 0.1]:
                            reduced_position_value = initial_position_value * reduction_factor
                            can_add_reduced, reduced_reason = await check_can_add_position(
                                reduced_position_value, self.db_manager, self.kalshi_client
                            )
                            
                            if can_add_reduced:
                                initial_position_value = reduced_position_value
                                self.logger.info(f"✅ Position size reduced to ${initial_position_value:.2f} to fit limits")
                                break
                        else:
                            # If even the smallest size doesn't fit, check if it's due to position count
                            from src.utils.position_limits import PositionLimitsManager
                            limits_manager = PositionLimitsManager(self.db_manager, self.kalshi_client)
                            current_positions = await limits_manager._get_position_count()
                            
                            if current_positions >= limits_manager.max_positions:
                                self.logger.debug(f"❌ POSITION COUNT LIMIT: {current_positions}/{limits_manager.max_positions} positions - cannot add new position")
                                results['failed_executions'] += 1
                                continue
                            else:
                                self.logger.debug(f"❌ POSITION SIZE LIMIT: Even minimum size ${initial_position_value * 0.1:.2f} exceeds limits")
                                results['failed_executions'] += 1
                                continue
                    
                    position_value = initial_position_value
                    self.logger.info(f"✅ POSITION LIMITS OK FOR ALLOCATION: ${position_value:.2f}")
                    
                    # Check cash reserves for this allocation
                    from src.utils.cash_reserves import check_can_trade_with_cash_reserves
                    
                    can_trade_reserves, reserves_reason = await check_can_trade_with_cash_reserves(
                        position_value, self.db_manager, self.kalshi_client
                    )
                    
                    if not can_trade_reserves:
                        self.logger.debug(f"❌ CASH RESERVES BLOCK ALLOCATION: {market_id} - {reserves_reason}")
                        results['failed_executions'] += 1
                        continue
                    
                    self.logger.info(f"✅ CASH RESERVES OK FOR ALLOCATION: {market_id}")
                    
                    # Get current market data
                    market_data = await self.kalshi_client.get_market(market_id)
                    if not market_data:
                        self.logger.warning(f"Could not get market data for {market_id}")
                        continue
                    
                    # FIXED: Extract from nested 'market' object
                    market_info = market_data.get('market', {})
                    
                    # CRITICAL FIX: Use get_entry_price() for correct ASK price when buying
                    # When BUYING, you pay the ASK price (what sellers want), not BID
                    from src.utils.price_utils import get_entry_price
                    price, price_valid = get_entry_price(market_info, intended_side)
                    
                    if not price_valid or price <= 0:
                        self.logger.warning(f"Invalid entry price for {market_id} {intended_side}: ${price:.3f}, skipping")
                        results['failed_executions'] += 1
                        continue
                    
                    # Calculate quantity
                    quantity = max(1, int(position_value / price))
                    
                    # Calculate proper stop-loss levels using Grok4 recommendations
                    from src.utils.stop_loss_calculator import StopLossCalculator
                    
                    # Calculate time to expiry for the market
                    time_to_expiry_days = 30  # Default fallback
                    try:
                        market_obj = next((m for m in opportunities if m.market_id == market_id), None)
                        if market_obj:
                            time_to_expiry_days = getattr(market_obj, 'time_to_expiry', 30)
                    except Exception as e:
                        self.logger.warning(f"Failed to get time_to_expiry for {market_id}, using default: {e}")
                    
                    exit_levels = StopLossCalculator.calculate_stop_loss_levels(
                        entry_price=price,
                        side=intended_side,
                        confidence=opportunity.confidence,
                        market_volatility=0.2,  # Default volatility estimate
                        time_to_expiry_days=time_to_expiry_days
                    )
                    
                    # Create Position object
                    position = Position(
                        market_id=market_id,
                        side=intended_side,
                        entry_price=price,
                        quantity=quantity,
                        timestamp=datetime.now(),
                        rationale=f"Portfolio optimization allocation: {allocation_fraction:.1%} of capital. Edge: {opportunity.edge:.3f}, Confidence: {opportunity.confidence:.3f}, Stop: {exit_levels['stop_loss_pct']}%",
                        confidence=opportunity.confidence,
                        live=False,  # Will be set to True after execution
                        strategy="portfolio_optimization",
                        
                        # Enhanced exit strategy using Grok4 recommendations
                        stop_loss_price=exit_levels['stop_loss_price'],
                        take_profit_price=exit_levels['take_profit_price'],
                        max_hold_hours=exit_levels['max_hold_hours'],
                        target_confidence_change=exit_levels['target_confidence_change']
                    )
                    
                    # Add position to database
                    position_id = await self.db_manager.add_position(position)
                    if position_id is None:
                        # This shouldn't happen now that we check above, but safety net
                        self.logger.warning(f"Position already exists for {market_id}, skipping execution")
                        continue
                    
                    position.id = position_id
                    
                    # Execute the position
                    live_mode = getattr(settings.trading, 'live_trading_enabled', False)
                    success = await execute_position(
                        position=position,
                        live_mode=live_mode,
                        db_manager=self.db_manager,
                        kalshi_client=self.kalshi_client
                    )
                    
                    if success:
                        results['successful_executions'] += 1
                        results['positions_created'] += 1
                        results['total_capital_used'] += position_value
                        self.logger.info(f"✅ Executed position: {market_id} {side} {quantity} at {price:.3f}")
                    else:
                        results['failed_executions'] += 1
                        self.logger.error(f"❌ Failed to execute position for {market_id}")
                
                except Exception as e:
                    self.logger.error(f"Error executing allocation for {market_id}: {e}")
                    results['failed_executions'] += 1
                    continue
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in portfolio allocation execution: {e}")
            return results

    async def _execute_arbitrage_strategy(self, markets: List[Market]) -> Dict:
        """
        Execute arbitrage opportunities.
        """
        try:
            self.logger.info("🎯 Executing Arbitrage Strategy...")
            
            # 1. Scan for opportunities
            opportunities = await self.arbitrage_scanner.scan_opportunities()
            
            if not opportunities:
                self.logger.info("No arbitrage opportunities found.")
                return {'arbitrage_trades': 0, 'arbitrage_profit': 0.0, 'arbitrage_exposure': 0.0}
            
            # 2. Sort by ROI and execute top ones
            opportunities.sort(key=lambda x: x.roi, reverse=True)
            
            total_profit = 0.0
            total_trades = 0
            total_exposure = 0.0
            
            # Limit number of arbitrage executions per cycle (configurable in settings)
            max_executions = settings.trading.arbitrage_max_executions
            
            live_mode = getattr(settings.trading, 'live_trading_enabled', False)
            
            for opp in opportunities[:max_executions]:
                # Check if we have enough capital allocated
                if total_exposure >= self.arbitrage_capital:
                    break
                    
                remaining_capital = self.arbitrage_capital - total_exposure
                
                # Execute
                result = await self.arbitrage_scanner.execute_arbitrage(opp, remaining_capital, live_mode=live_mode)
                
                if result.get('legs_filled', 0) > 0:
                    total_trades += 1
                    total_exposure += result.get('total_cost', 0.0)
                    total_profit += result.get('profit_locked', 0.0)
            
            self.logger.info(
                f"✅ Arbitrage: {total_trades} trades executed, "
                f"${total_exposure:.2f} exposure, "
                f"${total_profit:.2f} locked profit"
            )
            
            return {
                'arbitrage_trades': total_trades,
                'arbitrage_profit': total_profit,
                'arbitrage_exposure': total_exposure
            }
            
        except Exception as e:
            self.logger.error(f"Error in arbitrage strategy: {e}")
            return {'arbitrage_trades': 0, 'arbitrage_profit': 0.0}

    def _compile_unified_results(
        self, 
        market_making_results: Dict, 
        portfolio_allocation: PortfolioAllocation,
        quick_flip_results: Dict,
        arbitrage_results: Dict
    ) -> TradingSystemResults:
        """
        Compile results from all strategies into unified metrics.
        """
        try:
            # Calculate total metrics
            total_capital_used = (
                market_making_results.get('total_exposure', 0) +
                portfolio_allocation.total_capital_used +
                quick_flip_results.get('total_capital_used', 0) +
                arbitrage_results.get('arbitrage_exposure', 0)
            )
            
            # Weight expected returns by capital allocation
            mm_weight = market_making_results.get('total_exposure', 0) / (total_capital_used + 1e-8)
            dir_weight = portfolio_allocation.total_capital_used / (total_capital_used + 1e-8)
            qf_weight = quick_flip_results.get('total_capital_used', 0) / (total_capital_used + 1e-8)
            arb_weight = arbitrage_results.get('arbitrage_exposure', 0) / (total_capital_used + 1e-8)
            
            # Portfolio expected return (weighted average)
            portfolio_expected_return = (
                mm_weight * market_making_results.get('expected_profit', 0) +
                dir_weight * portfolio_allocation.expected_portfolio_return +
                qf_weight * quick_flip_results.get('expected_profit', 0) +
                arb_weight * arbitrage_results.get('arbitrage_profit', 0)
            )
            
            # Annualize expected return (assume positions held for 30 days average)
            expected_annual_return = portfolio_expected_return * (365 / 30)
            
            # Capital efficiency
            capital_efficiency = total_capital_used / self.total_capital
            
            # Total positions
            total_positions = (
                market_making_results.get('orders_placed', 0) // 2 +  # 2 orders per position
                len(portfolio_allocation.allocations) +
                quick_flip_results.get('positions_created', 0) +
                arbitrage_results.get('arbitrage_trades', 0)
            )
            
            return TradingSystemResults(
                # Market making
                market_making_orders=market_making_results.get('orders_placed', 0),
                market_making_exposure=market_making_results.get('total_exposure', 0),
                market_making_expected_profit=market_making_results.get('expected_profit', 0),
                
                # Directional trading
                directional_positions=len(portfolio_allocation.allocations),
                directional_exposure=portfolio_allocation.total_capital_used,
                directional_expected_return=portfolio_allocation.expected_portfolio_return,
                
                # Portfolio metrics
                total_capital_used=total_capital_used,
                portfolio_expected_return=portfolio_expected_return,
                portfolio_sharpe_ratio=portfolio_allocation.portfolio_sharpe,
                portfolio_volatility=portfolio_allocation.portfolio_volatility,
                
                # Risk metrics
                max_portfolio_drawdown=portfolio_allocation.max_portfolio_drawdown,
                correlation_score=1.0 - portfolio_allocation.diversification_ratio,
                diversification_ratio=portfolio_allocation.diversification_ratio,
                
                # Performance
                total_positions=total_positions,
                capital_efficiency=capital_efficiency,
                expected_annual_return=expected_annual_return
            )
            
        except Exception as e:
            self.logger.error(f"Error compiling results: {e}")
            return TradingSystemResults()

    async def _manage_risk_and_rebalance(self, results: TradingSystemResults):
        """
        Manage risk and rebalance portfolio if needed.
        """
        try:
            # Check risk constraints
            risk_violations = []
            
            if results.portfolio_volatility > self.config.max_portfolio_volatility:
                risk_violations.append(f"Portfolio vol {results.portfolio_volatility:.1%} > limit {self.config.max_portfolio_volatility:.1%}")
            
            if results.max_portfolio_drawdown > self.config.max_drawdown_limit:
                risk_violations.append(f"Max drawdown {results.max_portfolio_drawdown:.1%} > limit {self.config.max_drawdown_limit:.1%}")
            
            if results.correlation_score > self.config.max_correlation_exposure:
                risk_violations.append(f"Correlation {results.correlation_score:.1%} > limit {self.config.max_correlation_exposure:.1%}")
            
            if risk_violations:
                self.logger.warning(f"⚠️  Risk violations detected: {risk_violations}")
                # Implement automatic position sizing reduction
                # Reduce max position size by 20% for each violation (min 50% of original)
                reduction_factor = max(0.5, 1.0 - (0.2 * len(risk_violations)))
                reduced_max_position = self.config.max_single_position * reduction_factor
                self.logger.info(
                    f"🛡️ Reducing max position size from {self.config.max_single_position:.1%} "
                    f"to {reduced_max_position:.1%} due to {len(risk_violations)} risk violation(s)"
                )
                # Temporarily adjust the config for this session
                self._original_max_position = getattr(self, '_original_max_position', self.config.max_single_position)
                self.config.max_single_position = reduced_max_position
            elif hasattr(self, '_original_max_position'):
                # Restore original position sizing when no violations
                self.logger.info(f"✅ Risk violations cleared - restoring max position to {self._original_max_position:.1%}")
                self.config.max_single_position = self._original_max_position
            
            # Check if rebalancing is needed
            time_since_rebalance = datetime.now() - self.last_rebalance
            if time_since_rebalance.total_seconds() > (self.config.rebalance_frequency_hours * 3600):
                self.logger.info("🔄 Portfolio rebalancing triggered")
                # Implement rebalancing logic - log current allocation and performance
                await self._perform_portfolio_rebalance(results)
                self.last_rebalance = datetime.now()
            
            # Performance monitoring
            if results.portfolio_sharpe_ratio < self.config.target_sharpe_ratio * 0.5:
                self.logger.warning(f"⚠️  Low Sharpe ratio: {results.portfolio_sharpe_ratio:.2f}")
            
            if results.capital_efficiency < 0.8:
                self.logger.warning(f"⚠️  Low capital efficiency: {results.capital_efficiency:.1%}")
            
        except Exception as e:
            self.logger.error(f"Error in risk management: {e}")

    async def _perform_portfolio_rebalance(self, results: TradingSystemResults) -> None:
        """
        Perform portfolio rebalancing based on current positions and performance.
        
        This method:
        1. Analyzes current position allocation vs target allocation
        2. Identifies over-weighted and under-weighted positions
        3. Logs rebalancing recommendations
        4. Optionally closes positions that deviate significantly from targets
        """
        try:
            self.logger.info("📊 Starting portfolio rebalance analysis...")
            
            # Get current open positions
            positions = await self.db_manager.get_open_positions()
            
            if not positions:
                self.logger.info("No open positions to rebalance")
                return
            
            # Calculate current allocation by strategy
            strategy_allocations = {}
            total_position_value = 0.0
            
            for pos in positions:
                strategy = pos.strategy or 'unknown'
                position_value = pos.entry_price * pos.quantity
                total_position_value += position_value
                
                if strategy not in strategy_allocations:
                    strategy_allocations[strategy] = {
                        'value': 0.0,
                        'count': 0,
                        'positions': []
                    }
                
                strategy_allocations[strategy]['value'] += position_value
                strategy_allocations[strategy]['count'] += 1
                strategy_allocations[strategy]['positions'].append(pos)
            
            if total_position_value == 0:
                self.logger.info("No position value to rebalance")
                return
            
            # Log current allocation vs target
            self.logger.info(f"📈 Current Portfolio Allocation (Total: ${total_position_value:.2f}):")
            
            target_allocations = {
                'market_making': self.config.market_making_allocation,
                'portfolio_optimization': self.config.directional_trading_allocation,
                'directional_trading': self.config.directional_trading_allocation,
                'quick_flip_scalping': self.config.quick_flip_allocation,
                'arbitrage': self.config.arbitrage_allocation
            }
            
            rebalance_recommendations = []
            
            for strategy, data in strategy_allocations.items():
                current_pct = data['value'] / total_position_value
                target_pct = target_allocations.get(strategy, 0.0)
                deviation = current_pct - target_pct
                
                self.logger.info(
                    f"   • {strategy}: ${data['value']:.2f} ({current_pct:.1%}) | "
                    f"Target: {target_pct:.1%} | Deviation: {deviation:+.1%}"
                )
                
                # Flag significant deviations (>10% off target)
                if abs(deviation) > 0.10:
                    action = "REDUCE" if deviation > 0 else "INCREASE"
                    rebalance_recommendations.append({
                        'strategy': strategy,
                        'action': action,
                        'deviation': deviation,
                        'current_value': data['value'],
                        'positions': data['positions']
                    })
            
            # Log recommendations
            if rebalance_recommendations:
                self.logger.info("🔄 Rebalancing Recommendations:")
                for rec in rebalance_recommendations:
                    self.logger.info(
                        f"   • {rec['action']} {rec['strategy']}: "
                        f"Currently {abs(rec['deviation']):.1%} {'over' if rec['deviation'] > 0 else 'under'} target"
                    )
                
                # Automatic rebalancing: Close worst-performing positions in over-allocated strategies
                for rec in rebalance_recommendations:
                    if rec['action'] == 'REDUCE' and len(rec['positions']) > 1:
                        # Find position with lowest confidence or longest hold time
                        positions_to_evaluate = rec['positions']
                        
                        # Sort by confidence (lowest first) - close lowest confidence first
                        positions_sorted = sorted(
                            positions_to_evaluate,
                            key=lambda p: p.confidence or 0.5
                        )
                        
                        # Log suggestion but don't auto-close (conservative approach)
                        lowest_confidence_pos = positions_sorted[0]
                        self.logger.info(
                            f"   💡 Suggestion: Consider closing {lowest_confidence_pos.market_id} "
                            f"(confidence: {lowest_confidence_pos.confidence or 0:.2f}) to reduce {rec['strategy']} allocation"
                        )
            else:
                self.logger.info("✅ Portfolio allocation is within acceptable ranges")
            
            # Log overall portfolio health
            self.logger.info(
                f"📊 Portfolio Health Summary:\n"
                f"   • Total Positions: {len(positions)}\n"
                f"   • Total Value: ${total_position_value:.2f}\n"
                f"   • Capital Efficiency: {results.capital_efficiency:.1%}\n"
                f"   • Expected Return: {results.expected_annual_return:.1%}\n"
                f"   • Sharpe Ratio: {results.portfolio_sharpe_ratio:.2f}"
            )
            
        except Exception as e:
            self.logger.error(f"Error during portfolio rebalance: {e}")

    def get_system_performance_summary(self) -> Dict:
        """
        Get comprehensive system performance summary.
        """
        try:
            # Get individual strategy performance (only if initialized)
            mm_performance = {}
            if hasattr(self, 'market_maker') and self.market_maker:
                mm_performance = self.market_maker.get_performance_summary()
            
            return {
                'system_status': 'active',
                'total_capital': self.total_capital,
                'capital_allocation': {
                    'market_making': self.config.market_making_allocation,
                    'directional': self.config.directional_trading_allocation,
                    'arbitrage': self.config.arbitrage_allocation
                },
                'market_making_performance': mm_performance,
                'last_rebalance': self.last_rebalance.isoformat(),
                'risk_limits': {
                    'max_volatility': self.config.max_portfolio_volatility,
                    'max_drawdown': self.config.max_drawdown_limit,
                    'max_correlation': self.config.max_correlation_exposure
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance summary: {e}")
            return {}


async def run_unified_trading_system(
    db_manager: DatabaseManager,
    kalshi_client: KalshiClient,
    xai_client: XAIClient,
    config: Optional[TradingSystemConfig] = None
) -> TradingSystemResults:
    """
    Main entry point for the unified advanced trading system.
    
    This is the "Beast Mode" that orchestrates all strategies to maximize
    returns while optimally using all available capital.
    """
    logger = get_trading_logger("unified_trading_main")
    
    try:
        logger.info("🚀 Starting Unified Advanced Trading System")
        
        # Initialize system
        trading_system = UnifiedAdvancedTradingSystem(
            db_manager, kalshi_client, xai_client, config
        )
        
        # 🚨 CRITICAL: Initialize with dynamic balance from Kalshi
        await trading_system.async_initialize()
        
        # Execute unified strategy
        results = await trading_system.execute_unified_trading_strategy()
        
        # Log final summary
        logger.info(
            f"🎯 UNIFIED SYSTEM COMPLETE 🎯\n"
            f"📊 PERFORMANCE SUMMARY:\n"
            f"  • Total Positions: {results.total_positions}\n" 
            f"  • Capital Used: ${results.total_capital_used:.0f} ({results.capital_efficiency:.1%})\n"
            f"  • Expected Annual Return: {results.expected_annual_return:.1%}\n"
            f"  • Portfolio Sharpe Ratio: {results.portfolio_sharpe_ratio:.2f}\n"
            f"  • Portfolio Volatility: {results.portfolio_volatility:.1%}\n"
            f"  • Max Drawdown: {results.max_portfolio_drawdown:.1%}\n"
            f"  • Diversification Ratio: {results.diversification_ratio:.2f}\n"
            f"\n"
            f"💰 STRATEGY BREAKDOWN:\n"
            f"  • Market Making: {results.market_making_orders} orders, ${results.market_making_expected_profit:.2f} profit\n"
            f"  • Directional: {results.directional_positions} positions, ${results.directional_expected_return:.2f} return\n"
            f"\n"
            f"🚀 SYSTEM STATUS: BEAST MODE ACTIVATED! 🚀"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error in unified trading system: {e}")
        return TradingSystemResults() 