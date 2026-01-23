"""
Trade Execution Job

This job takes a position and executes it as a trade.
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict

from src.utils.database import DatabaseManager, Position, Order
from src.config.settings import settings
from src.utils.logging_setup import get_trading_logger, log_trade_execution
from src.clients.kalshi_client import KalshiClient, KalshiAPIError

async def execute_position(
    position: Position, 
    live_mode: bool, 
    db_manager: DatabaseManager, 
    kalshi_client: KalshiClient
) -> bool:
    """
    Executes a single trade position.
    
    Args:
        position: The position to execute.
        live_mode: Whether to execute a live or simulated trade.
        db_manager: The database manager instance.
        kalshi_client: The Kalshi client instance.
        
    Returns:
        True if execution was successful, False otherwise.
    """
    logger = get_trading_logger("trade_execution")
    logger.info(f"Executing position for market: {position.market_id}")
    
    client_order_id = str(uuid.uuid4())
    
    # Create order record for tracking
    order = Order(
        market_id=position.market_id,
        side=position.side,
        action="buy",
        order_type="market",
        quantity=position.quantity,
        price=position.entry_price,
        status="pending",
        client_order_id=client_order_id,
        created_at=datetime.now(),
        position_id=position.id
    )

    if live_mode:
        try:
            # Track the order in database
            order_id = await db_manager.add_order(order)
            
            # Convert entry price to cents for Kalshi API
            entry_price_cents = int(position.entry_price * 100)
            
            # Even market orders need a price parameter in Kalshi API
            order_params = {
                "ticker": position.market_id,
                "client_order_id": client_order_id,
                "side": position.side.lower(),
                "action": "buy",
                "count": position.quantity,
                "type_": "market"
            }
            
            # Add price parameter based on side (required by Kalshi API)
            if position.side.lower() == "yes":
                order_params["yes_price"] = entry_price_cents
            else:
                order_params["no_price"] = entry_price_cents
            
            order_response = await kalshi_client.place_order(**order_params)
            
            # For a market order, the fill price is not guaranteed.
            # A more robust implementation would query the /fills endpoint
            # to confirm the execution price after the fact.
            # For now, we will optimistically assume it fills at the entry price.
            fill_price = position.entry_price
            kalshi_order_id = order_response.get('order', {}).get('order_id')
            
            # Update order status to filled
            if order_id:
                await db_manager.update_order_status(
                    order_id, 
                    'filled', 
                    kalshi_order_id=kalshi_order_id,
                    fill_price=fill_price
                )

            await db_manager.update_position_to_live(position.id, fill_price)
            
            # Log trade execution with helper function
            log_trade_execution(
                action="BUY",
                market_id=position.market_id,
                amount=position.quantity,
                price=fill_price,
                confidence=position.confidence,
                reason=position.rationale,
                order_type="market",
                kalshi_order_id=kalshi_order_id,
                live_mode=True
            )
            
            logger.info(f"Successfully placed LIVE order for {position.market_id}. Order ID: {kalshi_order_id}")
            return True

        except KalshiAPIError as e:
            # Update order status to failed
            if order_id:
                await db_manager.update_order_status(order_id, 'failed')
            logger.error(f"Failed to place LIVE order for {position.market_id}: {e}")
            return False
    else:
        # Simulate the trade - still track the order
        order.status = "filled"
        order.filled_at = datetime.now()
        order.fill_price = position.entry_price
        await db_manager.add_order(order)
        
        await db_manager.update_position_to_live(position.id, position.entry_price)
        
        # Log simulated trade
        log_trade_execution(
            action="BUY",
            market_id=position.market_id,
            amount=position.quantity,
            price=position.entry_price,
            confidence=position.confidence,
            reason=position.rationale,
            order_type="market",
            live_mode=False
        )
        
        logger.info(f"Successfully placed SIMULATED order for {position.market_id}")
        return True


async def place_sell_limit_order(
    position: Position,
    limit_price: float,
    db_manager: DatabaseManager,
    kalshi_client: KalshiClient
) -> bool:
    """
    Place a sell limit order to close an existing position.
    
    Args:
        position: The position to close
        limit_price: The limit price for the sell order (in dollars)
        db_manager: Database manager
        kalshi_client: Kalshi API client
    
    Returns:
        True if order placed successfully, False otherwise
    """
    logger = get_trading_logger("sell_limit_order")
    
    try:
        client_order_id = str(uuid.uuid4())
        
        # Convert price to cents for Kalshi API
        limit_price_cents = int(limit_price * 100)
        
        # For sell orders, we need to use the opposite side logic:
        # - If we have YES position, we sell YES shares (action="sell", side="yes")
        # - If we have NO position, we sell NO shares (action="sell", side="no")
        side = position.side.lower()  # "YES" -> "yes", "NO" -> "no"
        
        # Create order record for tracking
        order = Order(
            market_id=position.market_id,
            side=position.side,
            action="sell",
            order_type="limit",
            quantity=position.quantity,
            price=limit_price,
            status="pending",
            client_order_id=client_order_id,
            created_at=datetime.now(),
            position_id=position.id
        )
        
        # Track the order in database
        db_order_id = await db_manager.add_order(order)
        
        order_params = {
            "ticker": position.market_id,
            "client_order_id": client_order_id,
            "side": side,
            "action": "sell",  # We're selling our existing position
            "count": position.quantity,
            "type_": "limit"
        }
        
        # Add the appropriate price parameter based on what we're selling
        if side == "yes":
            order_params["yes_price"] = limit_price_cents
        else:
            order_params["no_price"] = limit_price_cents
        
        logger.info(f"🎯 Placing SELL LIMIT order: {position.quantity} {side.upper()} at {limit_price_cents}¢ for {position.market_id}")
        
        # Place the sell limit order
        response = await kalshi_client.place_order(**order_params)
        
        if response and 'order' in response:
            kalshi_order_id = response['order'].get('order_id', client_order_id)
            
            # Update order status in database
            if db_order_id:
                await db_manager.update_order_status(
                    db_order_id, 
                    'placed', 
                    kalshi_order_id=kalshi_order_id
                )
            
            # Log trade execution
            log_trade_execution(
                action="SELL_LIMIT",
                market_id=position.market_id,
                amount=position.quantity,
                price=limit_price,
                reason=f"Limit sell order at {limit_price_cents}¢",
                order_type="limit",
                kalshi_order_id=kalshi_order_id,
                live_mode=True
            )
            
            logger.info(f"✅ SELL LIMIT ORDER placed successfully! Order ID: {kalshi_order_id}")
            logger.info(f"   Market: {position.market_id}")
            logger.info(f"   Side: {side.upper()} (selling {position.quantity} shares)")
            logger.info(f"   Limit Price: {limit_price_cents}¢")
            logger.info(f"   Expected Proceeds: ${limit_price * position.quantity:.2f}")
            
            return True
        else:
            # Update order status to failed
            if db_order_id:
                await db_manager.update_order_status(db_order_id, 'failed')
            logger.error(f"❌ Failed to place sell limit order: {response}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error placing sell limit order for {position.market_id}: {e}")
        return False


async def place_profit_taking_orders(
    db_manager: DatabaseManager,
    kalshi_client: KalshiClient,
    profit_threshold: float = 0.25  # 25% profit target
) -> Dict[str, int]:
    """
    Place sell limit orders for positions that have reached profit targets.
    
    Args:
        db_manager: Database manager
        kalshi_client: Kalshi API client
        profit_threshold: Minimum profit percentage to trigger sell order
    
    Returns:
        Dictionary with results: {'orders_placed': int, 'positions_processed': int}
    """
    logger = get_trading_logger("profit_taking")
    
    results = {'orders_placed': 0, 'positions_processed': 0}
    
    try:
        # Get all open live positions
        positions = await db_manager.get_open_live_positions()
        
        if not positions:
            logger.info("No open positions to process for profit taking")
            return results
        
        logger.info(f"📊 Checking {len(positions)} positions for profit-taking opportunities")
        
        for position in positions:
            try:
                # Check for existing active sell orders to prevent duplicates
                existing_orders = await db_manager.get_orders_by_position(position.id)
                has_active_sell = any(
                    o.action == 'sell' and o.status in ['pending', 'placed', 'submitted'] 
                    for o in existing_orders
                )
                
                if has_active_sell:
                    logger.debug(f"Skipping profit-taking for {position.market_id} - active sell order exists")
                    continue

                results['positions_processed'] += 1
                
                # Get current market data
                market_response = await kalshi_client.get_market(position.market_id)
                market_data = market_response.get('market', {})
                
                if not market_data:
                    logger.warning(f"Could not get market data for {position.market_id}")
                    continue
                
                # Get current price based on position side
                # API returns yes_bid/no_bid, not yes_price/no_price
                yes_bid = market_data.get('yes_bid', 0)
                no_bid = market_data.get('no_bid', 0)
                last_price = market_data.get('last_price', 50)
                
                if position.side == "YES":
                    current_price = (yes_bid if yes_bid > 0 else last_price) / 100  # Convert cents to dollars
                else:
                    current_price = (no_bid if no_bid > 0 else (100 - last_price)) / 100
                
                # Calculate current profit - guard against division by zero
                if current_price > 0 and position.entry_price > 0:
                    profit_pct = (current_price - position.entry_price) / position.entry_price
                    unrealized_pnl = (current_price - position.entry_price) * position.quantity
                    
                    logger.debug(f"Position {position.market_id}: Entry=${position.entry_price:.3f}, Current=${current_price:.3f}, Profit={profit_pct:.1%}, PnL=${unrealized_pnl:.2f}")
                    
                    # Check if we should place a profit-taking sell order
                    if profit_pct >= profit_threshold:
                        # Use "chasing limit order" strategy
                        # Start at mid-price or slightly better, then aggressive
                        # For now, we will be aggressive to secure the profit
                        # Cross the spread immediately to get filled (taker fee is worth it for profit taking)
                        if position.side == "YES":
                            # We are selling YES shares
                            # Bid price is what buyers are willing to pay us
                            # We should sell AT or slightly BELOW bid to ensure fill
                            best_bid = (yes_bid if yes_bid > 0 else last_price - 1) / 100
                            # If we use current_price (which uses bid logic), we are safer
                            # Use 1% below current price (bid) to ensure immediate execution
                            sell_price = current_price * 0.99
                        else:
                            # We are selling NO shares
                            # No bid is what buyes willing to pay
                            best_bid = (no_bid if no_bid > 0 else (100 - last_price) - 1) / 100
                            sell_price = current_price * 0.99
                        
                        # Safety check: ensure sell price is still profitable
                        # If crossing spread erodes all profit, hold or limit at mid
                        if sell_price <= position.entry_price * 1.05 and profit_pct > 0.10:
                            # If we have 10%+ profit but crossing spread kills it, use limit at mid
                            # But here we assume profit_threshold > 20% so we have buffer
                            sell_price = max(sell_price, position.entry_price * 1.05)

                        sell_price = max(0.01, sell_price)
                        
                        logger.info(f"💰 PROFIT TARGET HIT: {position.market_id} - {profit_pct:.1%} profit (${unrealized_pnl:.2f})")
                        
                        # Place sell limit order
                        success = await place_sell_limit_order(
                            position=position,
                            limit_price=sell_price,
                            db_manager=db_manager,
                            kalshi_client=kalshi_client
                        )
                        
                        if success:
                            results['orders_placed'] += 1
                            logger.info(f"✅ Profit-taking order placed for {position.market_id}")
                        else:
                            logger.error(f"❌ Failed to place profit-taking order for {position.market_id}")
                
            except Exception as e:
                logger.error(f"Error processing position {position.market_id} for profit taking: {e}")
                continue
        
        logger.info(f"🎯 Profit-taking summary: {results['orders_placed']} orders placed from {results['positions_processed']} positions")
        return results
        
    except Exception as e:
        logger.error(f"Error in profit-taking order placement: {e}")
        return results


async def place_stop_loss_orders(
    db_manager: DatabaseManager,
    kalshi_client: KalshiClient,
    stop_loss_threshold: float = -0.10  # 10% stop loss
) -> Dict[str, int]:
    """
    Place sell limit orders for positions that need stop-loss protection.
    
    Args:
        db_manager: Database manager
        kalshi_client: Kalshi API client
        stop_loss_threshold: Maximum loss percentage before triggering stop loss
    
    Returns:
        Dictionary with results: {'orders_placed': int, 'positions_processed': int}
    """
    logger = get_trading_logger("stop_loss_orders")
    
    results = {'orders_placed': 0, 'positions_processed': 0}
    
    try:
        # Get all open live positions
        positions = await db_manager.get_open_live_positions()
        
        if not positions:
            logger.info("No open positions to process for stop-loss orders")
            return results
        
        logger.info(f"🛡️ Checking {len(positions)} positions for stop-loss protection")
        
        for position in positions:
            try:
                # Check for existing active sell orders to prevent duplicates
                existing_orders = await db_manager.get_orders_by_position(position.id)
                has_active_sell = any(
                    o.action == 'sell' and o.status in ['pending', 'placed', 'submitted'] 
                    for o in existing_orders
                )
                
                if has_active_sell:
                    logger.debug(f"Skipping stop-loss for {position.market_id} - active sell order exists")
                    continue

                results['positions_processed'] += 1
                
                # Get current market data
                market_response = await kalshi_client.get_market(position.market_id)
                market_data = market_response.get('market', {})
                
                if not market_data:
                    logger.warning(f"Could not get market data for {position.market_id}")
                    continue
                
                # Get current price based on position side
                # API returns yes_bid/no_bid, not yes_price/no_price
                yes_bid = market_data.get('yes_bid', 0)
                no_bid = market_data.get('no_bid', 0)
                last_price = market_data.get('last_price', 50)
                
                if position.side == "YES":
                    current_price = (yes_bid if yes_bid > 0 else last_price) / 100
                else:
                    current_price = (no_bid if no_bid > 0 else (100 - last_price)) / 100
                
                # Calculate current loss - guard against division by zero
                if current_price > 0 and position.entry_price > 0:
                    loss_pct = (current_price - position.entry_price) / position.entry_price
                    unrealized_pnl = (current_price - position.entry_price) * position.quantity
                    
                    # Check if we need stop-loss protection
                    if loss_pct <= stop_loss_threshold:  # Negative loss percentage
                        # Calculate stop-loss sell price
                        # CRITICAL FIX: Use current_price for stop loss, not entry_price
                        # We need to cross the spread to exit immediately
                        stop_price = current_price * 0.95  # 5% below current price to ensure fill
                        stop_price = max(0.01, stop_price)  # Ensure price is at least 1¢
                        
                        logger.info(f"🛡️ STOP LOSS TRIGGERED: {position.market_id} - {loss_pct:.1%} loss (${unrealized_pnl:.2f})")
                        
                        # Place stop-loss sell order
                        success = await place_sell_limit_order(
                            position=position,
                            limit_price=stop_price,
                            db_manager=db_manager,
                            kalshi_client=kalshi_client
                        )
                        
                        if success:
                            results['orders_placed'] += 1
                            logger.info(f"✅ Stop-loss order placed for {position.market_id}")
                        else:
                            logger.error(f"❌ Failed to place stop-loss order for {position.market_id}")
                
            except Exception as e:
                logger.error(f"Error processing position {position.market_id} for stop loss: {e}")
                continue
        
        logger.info(f"🛡️ Stop-loss summary: {results['orders_placed']} orders placed from {results['positions_processed']} positions")
        return results
        
    except Exception as e:
        logger.error(f"Error in stop-loss order placement: {e}")
        return results
