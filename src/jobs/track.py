"""
Position Tracking Job

This job monitors open positions and implements smart exit strategies:
- Market resolution (original)
- Stop-loss exits
- Take-profit exits  
- Time-based exits
- Confidence-based exits
- Periodic database sync with Kalshi (every 5 minutes)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from src.utils.database import DatabaseManager, Position, TradeLog
from src.config.settings import settings
from src.utils.logging_setup import setup_logging, get_trading_logger, log_trade_execution
from src.clients.kalshi_client import KalshiClient

# Last sync timestamp for periodic syncing
_last_db_sync = None
_sync_interval_seconds = 300  # 5 minutes

async def sync_database_with_kalshi(db_manager: DatabaseManager, kalshi_client: KalshiClient) -> dict:
    """
    Periodic database sync to ensure positions match Kalshi's real-time data.
    Runs every 5 minutes to catch any discrepancies.
    
    Returns:
        Dict with sync results: {'synced': int, 'closed': int, 'errors': int}
    """
    logger = get_trading_logger("db_sync")
    results = {'synced': 0, 'closed': 0, 'errors': 0}
    
    try:
        # Get Kalshi positions
        positions_response = await kalshi_client.get_positions()
        kalshi_positions = positions_response.get('market_positions', [])
        
        # Build set of active Kalshi market IDs
        kalshi_active = set()
        for pos in kalshi_positions:
            if pos.get('position', 0) != 0:
                kalshi_active.add(pos.get('ticker'))
        
        # Get database positions
        db_positions = await db_manager.get_open_positions()
        
        # Check for positions in DB but not on Kalshi (need to close)
        for db_pos in db_positions:
            if db_pos.market_id not in kalshi_active:
                # This position closed on Kalshi but still open in DB
                await db_manager.update_position_status(db_pos.id, 'closed')
                results['closed'] += 1
                logger.info(f"Closed stale position: {db_pos.market_id} (not on Kalshi)")
        
        # Check for positions on Kalshi but not in DB (add them)
        for kalshi_pos in kalshi_positions:
            ticker = kalshi_pos.get('ticker')
            position_count = kalshi_pos.get('position', 0)
            
            if position_count != 0 and ticker:
                side = 'YES' if position_count > 0 else 'NO'
                db_pos = await db_manager.get_position_by_market_and_side(ticker, side)
                
                if not db_pos:
                    # Position exists on Kalshi but not in DB - create it
                    try:
                        market_data = await kalshi_client.get_market(ticker)
                        market_info = market_data.get('market', {})
                        
                        # CRITICAL FIX: Kalshi API uses yes_bid/no_bid, NOT yes_price/no_price
                        # Fallback chain: bid -> ask -> last_price
                        if side == 'YES':
                            price = (market_info.get('yes_bid', 0) or market_info.get('yes_ask', 0) 
                                    or market_info.get('last_price', 50)) / 100
                        else:
                            price = (market_info.get('no_bid', 0) or market_info.get('no_ask', 0) 
                                    or (100 - market_info.get('last_price', 50))) / 100
                        
                        new_position = Position(
                            market_id=ticker,
                            side=side,
                            entry_price=price,
                            quantity=abs(position_count),
                            timestamp=datetime.now(),
                            rationale="Synced from Kalshi during periodic sync",
                            confidence=0.5,
                            live=True,
                            status='open',
                            strategy='sync_recovery'
                        )
                        
                        await db_manager.add_position(new_position)
                        results['synced'] += 1
                        logger.info(f"Synced missing position from Kalshi: {ticker} {side}")
                        
                    except Exception as e:
                        logger.error(f"Error syncing position {ticker}: {e}")
                        results['errors'] += 1
        
        if results['synced'] > 0 or results['closed'] > 0:
            logger.info(f"Database sync complete: {results}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error during database sync: {e}")
        results['errors'] += 1
        return results

async def should_exit_position(
    position: Position, 
    current_yes_price: float, 
    current_no_price: float, 
    market_status: str,
    market_result: str = None
) -> tuple[bool, str, float]:
    """
    Determine if position should be exited based on smart exit strategies.
    
    Returns:
        (should_exit, exit_reason, exit_price)
    """
    current_price = current_yes_price if position.side == "YES" else current_no_price
    
    # 1. Market resolution (original logic)
    if market_status == 'closed':
        # If market resolved, use the result to determine exit price
        if market_result:
            exit_price = 1.0 if market_result == position.side else 0.0
        else:
            # Fallback to current price if no result available
            exit_price = current_price
        return True, "market_resolution", exit_price
    
    # 1.5 CRITICAL FIX: Detect market resolution - SIMPLIFIED VERSION
    # Only trigger if price is EXACTLY 0.00 or 1.00 (not 0.01 or 0.99)
    # The original bot doesn't have this aggressive check
    if current_price == 0.0 or current_price == 1.0:
        # Price at exact extreme indicates market resolution
        if position.side == "YES":
            exit_price = 1.0 if current_yes_price == 1.0 else 0.0
        else:
            exit_price = 1.0 if current_no_price == 1.0 else 0.0
        return True, "market_resolution_confirmed", exit_price
    
    # 2. ENHANCED Stop-loss exit using proper logic for YES/NO positions
    if position.stop_loss_price:
        from src.utils.stop_loss_calculator import StopLossCalculator
        
        should_trigger = StopLossCalculator.is_stop_loss_triggered(
            position_side=position.side,
            entry_price=position.entry_price,
            current_price=current_price,
            stop_loss_price=position.stop_loss_price
        )
        
        if should_trigger:
            # Calculate the actual loss to log it
            expected_pnl = StopLossCalculator.calculate_pnl_at_stop_loss(
                entry_price=position.entry_price,
                stop_loss_price=position.stop_loss_price,
                quantity=position.quantity,
                side=position.side
            )
            return True, f"stop_loss_triggered_pnl_{expected_pnl:.2f}", current_price
    
    # 3. Take-profit exit (same logic for YES and NO)
    # When you OWN any contract, you profit by selling at a HIGHER price
    if position.take_profit_price:
        # For BOTH YES and NO positions, take profit when price rises above target
        take_profit_triggered = current_price >= position.take_profit_price
        
        # SANITY CHECK: Only call it "take_profit" if we're actually profiting!
        # Calculate expected PnL to verify this is truly a profitable exit
        if take_profit_triggered:
            expected_pnl = (current_price - position.entry_price) * position.quantity
            if expected_pnl > 0:
                return True, "take_profit", current_price
            else:
                # This would be a loss, not a profit - something is wrong
                # This likely means the market resolved against us but API status isn't updated
                # Don't trigger take_profit - let market resolution logic handle it
                pass  # Fall through to other checks
    
    # 4. Time-based exit
    if position.max_hold_hours:
        hours_held = (datetime.now() - position.timestamp).total_seconds() / 3600
        if hours_held >= position.max_hold_hours:
            return True, "time_based", current_price
    
    # 5. Emergency exit for positions without stop-loss (legacy positions)
    if not position.stop_loss_price:
        # Calculate emergency stop-loss at 10% loss
        from src.utils.stop_loss_calculator import StopLossCalculator
        emergency_stop = StopLossCalculator.calculate_simple_stop_loss(
            entry_price=position.entry_price,
            side=position.side,
            stop_loss_pct=0.10  # 10% emergency stop
        )
        
        emergency_triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side=position.side,
            entry_price=position.entry_price,
            current_price=current_price,
            stop_loss_price=emergency_stop
        )
        
        if emergency_triggered:
            return True, "emergency_stop_loss_10pct", current_price
    
    # 6. Confidence-based exit (placeholder - would need re-analysis)
    # This would require periodic re-analysis, which we're avoiding for cost reasons
    # Could be implemented as a separate, less frequent job
    
    return False, "", current_price

async def calculate_dynamic_exit_levels(position: Position) -> dict:
    """Calculate smart exit levels using Grok4 recommendations."""
    from src.utils.stop_loss_calculator import StopLossCalculator
    
    # Use the centralized stop-loss calculator
    exit_levels = StopLossCalculator.calculate_stop_loss_levels(
        entry_price=position.entry_price,
        side=position.side,
        confidence=position.confidence or 0.7,
        market_volatility=0.2,  # Default volatility estimate
        time_to_expiry_days=30.0  # Default time estimate
    )
    
    return exit_levels

async def run_tracking(db_manager: Optional[DatabaseManager] = None):
    """
    Enhanced position tracking with smart exit strategies and sell limit orders.
    
    Args:
        db_manager: Optional DatabaseManager instance for testing.
    """
    global _last_db_sync
    
    logger = get_trading_logger("position_tracking")
    logger.info("Starting enhanced position tracking job with sell limit orders.")

    if db_manager is None:
        db_manager = DatabaseManager()
        await db_manager.initialize()

    kalshi_client = KalshiClient()

    try:
        # Step 0: Periodic database sync (every 5 minutes)
        now = datetime.now()
        if _last_db_sync is None or (now - _last_db_sync).total_seconds() >= _sync_interval_seconds:
            logger.info("🔄 Running periodic database sync with Kalshi...")
            sync_results = await sync_database_with_kalshi(db_manager, kalshi_client)
            _last_db_sync = now
            
            if sync_results['synced'] > 0 or sync_results['closed'] > 0:
                logger.info(
                    f"✅ Database sync: {sync_results['synced']} positions synced, "
                    f"{sync_results['closed']} stale positions closed"
                )
        
        # Step 1: Place sell limit orders for profit-taking and stop-loss
        from src.jobs.execute import place_profit_taking_orders, place_stop_loss_orders
        
        logger.info("🎯 Checking for profit-taking opportunities...")
        profit_results = await place_profit_taking_orders(
            db_manager=db_manager,
            kalshi_client=kalshi_client,
            profit_threshold=0.20  # 20% profit target
        )
        
        logger.info("🛡️ Checking for stop-loss protection...")
        stop_loss_results = await place_stop_loss_orders(
            db_manager=db_manager,
            kalshi_client=kalshi_client,
            stop_loss_threshold=-0.15  # 15% stop loss
        )
        
        total_sell_orders = profit_results['orders_placed'] + stop_loss_results['orders_placed']
        if total_sell_orders > 0:
            logger.info(f"📈 SELL LIMIT ORDERS SUMMARY: {total_sell_orders} orders placed")
            logger.info(f"   Profit-taking: {profit_results['orders_placed']} orders")
            logger.info(f"   Stop-loss: {stop_loss_results['orders_placed']} orders")
        
        # Step 2: Continue with existing position tracking (market resolution, etc.)
        open_positions = await db_manager.get_open_live_positions()

        if not open_positions:
            logger.info("No open positions to track.")
            return

        # Count tracked vs untracked for visibility
        tracked_count = sum(1 for pos in open_positions if getattr(pos, 'tracked', True))
        untracked_count = len(open_positions) - tracked_count
        
        logger.info(
            f"Found {len(open_positions)} open positions to track: "
            f"{tracked_count} tracked (full P&L), {untracked_count} untracked (monitoring only)"
        )

        exits_executed = 0
        for position in open_positions:
            try:
                # Get current market data
                market_response = await kalshi_client.get_market(position.market_id)
                market_data = market_response.get('market', {})

                if not market_data:
                    logger.warning(f"Could not retrieve market data for {position.market_id}. Skipping.")
                    continue

                # Get current prices
                # CRITICAL FIX: Kalshi API uses yes_bid/no_bid, NOT yes_price/no_price!
                # The old code used non-existent fields, causing exit_price=0 for all trades
                yes_bid = market_data.get('yes_bid', 0) or 0
                no_bid = market_data.get('no_bid', 0) or 0
                last_price = market_data.get('last_price', 50)
                
                # Use bid price for exit (what buyers are willing to pay)
                # Fallback to last_price if no bid available
                current_yes_price = (yes_bid if yes_bid > 0 else last_price) / 100
                current_no_price = (no_bid if no_bid > 0 else (100 - last_price)) / 100
                
                market_status = market_data.get('status', 'unknown')
                market_result = market_data.get('result')  # Market resolution result
                
                # If position doesn't have exit strategy set, calculate defaults
                if not position.stop_loss_price and not position.take_profit_price:
                    logger.info(f"Setting up exit strategy for position {position.market_id}")
                    exit_levels = await calculate_dynamic_exit_levels(position)
                    
                    # Update position with exit strategy (this would need a new DB method)
                # NOTE: Exit strategies apply to BOTH tracked and untracked positions
                # Untracked positions still need stop losses, take profit, time-based exits for risk management
                    # For now, we'll apply them dynamically
                    position.stop_loss_price = exit_levels["stop_loss_price"]
                    position.take_profit_price = exit_levels["take_profit_price"] 
                    position.max_hold_hours = exit_levels["max_hold_hours"]
                    position.target_confidence_change = exit_levels["target_confidence_change"]

                # Check if position should be exited (market resolution, time-based, etc.)
                should_exit, exit_reason, exit_price = await should_exit_position(
                    position, current_yes_price, current_no_price, market_status, market_result
                )

                if should_exit:
                    # Check if position is tracked (skip trade logs for untracked/legacy positions)
                    is_tracked = getattr(position, 'tracked', True)  # Default to True for backward compatibility
                    
                    if not is_tracked:
                        logger.info(
                            f"Closing UNTRACKED position {position.market_id} (no trade log will be created). "
                            f"Entry: {position.entry_price:.3f}, Exit: {exit_price:.3f}"
                        )
                        # Just close the position without creating a trade log
                        await db_manager.update_position_status(position.id, 'closed')
                        logger.info(f"Position {position.market_id} closed (untracked - no P&L recorded)")
                        continue
                    
                    logger.info(
                        f"Exiting position {position.market_id} due to {exit_reason}. "
                        f"Entry: {position.entry_price:.3f}, Exit: {exit_price:.3f}"
                    )
                    
                    # Calculate PnL and slippage
                    pnl = (exit_price - position.entry_price) * position.quantity
                    # Slippage = difference between expected exit (take_profit or stop_loss) and actual
                    slippage = None
                    if exit_reason == "take_profit" and position.take_profit_price:
                        slippage = exit_price - position.take_profit_price
                    elif "stop_loss" in exit_reason and position.stop_loss_price:
                        slippage = exit_price - position.stop_loss_price
                    
                    # Create trade log with explicit exit_reason
                    trade_log = TradeLog(
                        market_id=position.market_id,
                        side=position.side,
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        quantity=position.quantity,
                        pnl=pnl,
                        entry_timestamp=position.timestamp,
                        exit_timestamp=datetime.now(),
                        rationale=position.rationale,
                        strategy=position.strategy,
                        exit_reason=exit_reason,
                        slippage=slippage
                    )

                    # Record the exit
                    await db_manager.add_trade_log(trade_log)
                    await db_manager.update_position_status(position.id, 'closed')
                    
                    # Log trade execution with helper function
                    log_trade_execution(
                        action="EXIT",
                        market_id=position.market_id,
                        amount=position.quantity,
                        price=exit_price,
                        reason=exit_reason,
                        pnl=pnl,
                        slippage=slippage
                    )
                    
                    exits_executed += 1
                    logger.info(
                        f"Position for market {position.market_id} closed via {exit_reason}. "
                        f"PnL: ${pnl:.2f}"
                    )
                else:
                    # Log current position status for monitoring
                    current_price = current_yes_price if position.side == "YES" else current_no_price
                    unrealized_pnl = (current_price - position.entry_price) * position.quantity
                    hours_held = (datetime.now() - position.timestamp).total_seconds() / 3600
                    
                    logger.debug(
                        f"Position {position.market_id} status: "
                        f"Entry: {position.entry_price:.3f}, Current: {current_price:.3f}, "
                        f"Unrealized P&L: ${unrealized_pnl:.2f}, Hours held: {hours_held:.1f}"
                    )

            except Exception as e:
                logger.error(f"Failed to process position for market {position.market_id}.", error=str(e))

        logger.info(f"Position tracking completed. Sell orders: {total_sell_orders}, Market exits: {exits_executed}")

    except Exception as e:
        logger.error("Error in position tracking job.", error=str(e), exc_info=True)
    finally:
        await kalshi_client.close()

if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_tracking())
