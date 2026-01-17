"""
Position Tracking Job

This job monitors open positions and implements smart exit strategies:
- Market resolution (original)
- Stop-loss exits
- Take-profit exits  
- Time-based exits
- Confidence-based exits
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from src.utils.database import DatabaseManager, Position, TradeLog
from src.config.settings import settings
from src.utils.logging_setup import setup_logging, get_trading_logger, log_trade_execution
from src.clients.kalshi_client import KalshiClient

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
    
    # 1.5 CRITICAL FIX: Detect market resolution even if status not yet 'closed'
    # If price is 0.00 or 1.00, the market has effectively resolved
    # This prevents false "take_profit" triggers when market resolves against us
    if current_price <= 0.01 or current_price >= 0.99:
        # Price at extreme (0 or 1) indicates market resolution
        # Determine if we won or lost based on price
        if position.side == "YES":
            # YES position: wins if yes_price = 1.00, loses if yes_price = 0.00
            if current_yes_price >= 0.99:
                exit_price = 1.0  # We won
            else:
                exit_price = 0.0  # We lost
        else:
            # NO position: wins if no_price = 1.00 (yes_price = 0.00), loses if no_price = 0.00
            if current_no_price >= 0.99:
                exit_price = 1.0  # We won
            else:
                exit_price = 0.0  # We lost
        return True, "market_resolution_by_price", exit_price
    
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
    logger = get_trading_logger("position_tracking")
    logger.info("Starting enhanced position tracking job with sell limit orders.")

    if db_manager is None:
        db_manager = DatabaseManager()
        await db_manager.initialize()

    kalshi_client = KalshiClient()

    try:
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

        logger.info(f"Found {len(open_positions)} open positions to track.")

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
                current_yes_price = market_data.get('yes_price', 0) / 100  # Convert cents to dollars
                current_no_price = market_data.get('no_price', 0) / 100
                market_status = market_data.get('status', 'unknown')
                market_result = market_data.get('result')  # Market resolution result
                
                # If position doesn't have exit strategy set, calculate defaults
                if not position.stop_loss_price and not position.take_profit_price:
                    logger.info(f"Setting up exit strategy for position {position.market_id}")
                    exit_levels = await calculate_dynamic_exit_levels(position)
                    
                    # Update position with exit strategy (this would need a new DB method)
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
