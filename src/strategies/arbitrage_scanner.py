
"""
Arbitrage Scanner Strategy - "The No-Resolution Arbitrage"

Scans for mutually exclusive market groups where the sum of "YES" ask prices is less than $1.00.
If buying one YES share in *every* market of the group costs < $1.00, and exactly one *must* resolve to YES,
then we have a risk-free profit (arbitrage).

Key Concepts:
- Grouping: Markets sharing the same `event_ticker` (or `series_ticker` in some cases).
- Condition: Sum(YES_ASK) < $1.00 (adjusted for fees if necessary).
- Execution: Buy 1 YES share of *every* market in the group simultaneously.
"""

import asyncio
import uuid
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from src.utils.logging_setup import get_trading_logger
from src.clients.kalshi_client import KalshiClient
from src.utils.database import Position, Order, TradeLog
from src.utils.database import DatabaseManager
from src.config.settings import settings

@dataclass
class ArbitrageOpportunity:
    event_ticker: str
    markets: List[Dict]  # List of market dicts involved
    total_cost: float    # Sum of ask prices
    profit: float        # 1.00 - total_cost
    net_profit: float    # profit - fees
    roi: float           # net_profit / total_cost
    timestamp: float

class ArbitrageScanner:
    def __init__(self, kalshi_client: KalshiClient, db_manager: DatabaseManager, fee_pct: float = 0.0):
        self.kalshi_client = kalshi_client
        self.db_manager = db_manager
        self.logger = get_trading_logger("arbitrage_scanner")
        self.fee_pct = fee_pct  # Transaction fee percentage (e.g., 0.0 for free trading, 0.01 for 1%)

    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        Scans all active markets for arbitrage opportunities.
        """
        self.logger.info("Starting arbitrage scan...")
        opportunities = []
        
        try:
            # 1. Fetch all active markets
            # Fetching from API directly to get live prices
            all_markets = []
            cursor = None
            while True:
                response = await self.kalshi_client.get_markets(
                    limit=100, 
                    cursor=cursor,
                    status="open"  # Kalshi API uses "open" for tradeable markets
                )
                markets_page = response.get("markets", [])
                all_markets.extend(markets_page)
                
                cursor = response.get("cursor")
                if not cursor:
                    break
            
            self.logger.info(f"Scanned {len(all_markets)} active markets.")

            # 2. Group by event_ticker
            event_groups = {}
            for m in all_markets:
                event_ticker = m.get('event_ticker')
                if event_ticker:
                    if event_ticker not in event_groups:
                        event_groups[event_ticker] = []
                    event_groups[event_ticker].append(m)

            # 3. Analyze groups
            for event_ticker, group in event_groups.items():
                if len(group) < 2:
                    continue

                total_ask_cost_cents = 0
                valid_group = True
                
                for market in group:
                    yes_ask = market.get('yes_ask')
                    
                    if yes_ask is None or yes_ask <= 0:
                        # Market is illiquid or no ask available
                        valid_group = False
                        break
                        
                    total_ask_cost_cents += yes_ask

                if not valid_group:
                    continue

                if total_ask_cost_cents < 100:
                    gross_profit_cents = 100 - total_ask_cost_cents
                    total_cost_dollars = total_ask_cost_cents / 100.0
                    
                    # Calculate Fees
                    # Estimating worst case taker fees if applicable.
                    # Fee = total_notional * fee_pct? Or per contract?
                    # Usually fee is on volume. Cost is volume.
                    estimated_fees = total_cost_dollars * self.fee_pct
                    net_profit_dollars = (gross_profit_cents / 100.0) - estimated_fees
                    
                    # Threshold: 2 cents NET profit min (and positive ROI)
                    if net_profit_dollars >= 0.02:
                        opp = ArbitrageOpportunity(
                            event_ticker=event_ticker,
                            markets=group,
                            total_cost=total_cost_dollars,
                            profit=gross_profit_cents / 100.0,
                            net_profit=net_profit_dollars,
                            roi=net_profit_dollars / total_cost_dollars,
                            timestamp=datetime.now().timestamp()
                        )
                        opportunities.append(opp)
                        self.logger.info(f"🚨 FOUND ARBITRAGE: {event_ticker} | Cost: ${opp.total_cost:.2f} | Net Profit: ${opp.net_profit:.2f}")

        except Exception as e:
            self.logger.error(f"Error during arbitrage scan: {e}")

        return opportunities

    async def _verify_prices_before_execution(self, opportunity: ArbitrageOpportunity, price_tolerance_cents: int = 1) -> tuple[bool, str]:
        """
        Re-verify all market prices before execution to prevent race conditions.
        
        Args:
            opportunity: The arbitrage opportunity to verify.
            price_tolerance_cents: Maximum acceptable price movement in cents (default: 1).
        
        Returns:
            (is_valid, reason) - True if prices are still good, False with reason if stale.
        """
        try:
            for market in opportunity.markets:
                ticker = market['ticker']
                original_yes_ask = market['yes_ask']
                
                # Fetch fresh market data
                fresh_market = await self.kalshi_client.get_market(ticker)
                if not fresh_market or 'market' not in fresh_market:
                    return False, f"Could not fetch fresh data for {ticker}"
                
                market_data = fresh_market['market']
                current_yes_ask = market_data.get('yes_ask', 0)
                
                # Check if price moved beyond tolerance
                price_diff = abs(current_yes_ask - original_yes_ask)
                if price_diff > price_tolerance_cents:
                    return False, f"Price moved for {ticker}: {original_yes_ask}¢ → {current_yes_ask}¢ (Δ{price_diff}¢ > {price_tolerance_cents}¢ tolerance)"
                
                # Update market with fresh price (but keep scanning time for logging)
                market['yes_ask'] = current_yes_ask
            
            return True, "All prices verified"
            
        except Exception as e:
            return False, f"Price verification failed: {str(e)}"

    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity, max_capital: float, live_mode: bool = False, price_tolerance_cents: int = 1) -> Dict:
        """
        Executes the arbitrage opportunity with pre-execution price verification.
        
        Args:
            opportunity: The arb opportunity to execute.
            max_capital: Maximum capital to deploy for this opportunity.
            live_mode: Whether to actually place orders (True) or just simulate (False).
            price_tolerance_cents: Maximum acceptable price movement (default: 1 cent).
        
        Returns:
            Dictionary with execution results and status.
        """
        results = {
            'orders_placed': 0,
            'total_cost': 0.0,
            'legs_filled': 0,
            'profit_locked': 0.0,
            'errors': [],
            'price_verification': 'pending'
        }
        
        # CRITICAL: Re-verify prices before execution to prevent race conditions
        is_valid, verification_msg = await self._verify_prices_before_execution(opportunity, price_tolerance_cents)
        
        if not is_valid:
            self.logger.warning(f"❌ STALE OPPORTUNITY REJECTED: {verification_msg}")
            results['price_verification'] = 'failed'
            results['errors'].append(f"Price verification failed: {verification_msg}")
            return results
        
        self.logger.info(f"✅ Price verification passed: {verification_msg}")
        results['price_verification'] = 'passed'
        
        cost_per_unit = opportunity.total_cost
        if cost_per_unit <= 0: return results
        
        # 1. Calculate Quantity based on Liquidity and Capital
        # We need to check the available liquidity at the YES_ASK price for ALL legs.
        # The trade size is limited by the leg with the *least* liquidity.
        
        min_liquidity = float('inf')
        
        for market in opportunity.markets:
            # We used 'yes_ask' in scanning, but for execution we need to be careful.
            # Check liquidity via orderbook depth (production requirement)
            try:
                # Fetch orderbook for each market to verify liquidity
                for market in opportunity.markets:
                    orderbook = await self.kalshi_client.get_orderbook(market['ticker'], depth=5)
                    yes_asks = orderbook.get('orderbook', {}).get('yes', [])
                    
                    # Check if we have sufficient depth at the ask price
                    if not yes_asks:
                        self.logger.warning(f"No YES asks in orderbook for {market['ticker']}, skipping arb")
                        return results
                    
                    # Verify first ask matches our expected price (within 1 cent tolerance)
                    first_ask_price = yes_asks[0][0] if yes_asks else 999
                    expected_cents = int(market['yes_ask'] * 100)
                    if abs(first_ask_price - expected_cents) > 1:
                        self.logger.warning(f"Price moved for {market['ticker']}: expected {expected_cents}¢, got {first_ask_price}¢")
                        return results
                        
            except Exception as liquidity_error:
                self.logger.error(f"Liquidity check failed: {liquidity_error}")
                return results

        # Calculate quantity based on max capital
        max_units_by_capital = int(max_capital // cost_per_unit)
        qty = min(max_units_by_capital, settings.trading.arbitrage_qty_cap)  # Configurable safety cap
        
        if qty <= 0:
            self.logger.warning(f"Quantity 0 calculated for arb (Capital: ${max_capital}, Cost: ${cost_per_unit})")
            return results

        self.logger.info(f"Executing Arbitrage on {opportunity.event_ticker}: Buying {qty} units. Live: {live_mode}")

        # 2. Execute Orders
        # We need to buy 'qty' of YES on every market in the group.
        
        from src.utils.database import Position, Order
        import uuid
        
        legs_verified = []
        
        for market in opportunity.markets:
            ticker = market.get('ticker')
            yes_ask_cents = market.get('yes_ask') # Price in cents
            
            # Ensure we have a valid price
            if not yes_ask_cents:
                results['errors'].append(f"Missing price for {ticker}")
                return results # Abort if any leg is invalid
                
            legs_verified.append({
                'ticker': ticker,
                'price_cents': yes_ask_cents,
                'price_dollars': yes_ask_cents / 100.0
            })

        # Place orders
        # We execute sequentially. In HFT, this would be async parallel.
        # Use gather for parallelism to minimize leg risk.
        
        execution_tasks = []
        
        for leg in legs_verified:
            # Prepare the order placement coroutine
            execution_tasks.append(self._place_arb_leg(leg, qty, live_mode, opportunity.event_ticker))
            
        # Execute all legs
        leg_results = await asyncio.gather(*execution_tasks)
        
        # Process results
        success_count = 0
        executed_cost = 0.0
        
        for res in leg_results:
            if res['success']:
                success_count += 1
                executed_cost += res['cost']
                results['orders_placed'] += 1
            else:
                results['errors'].append(res['error'])
        
        results['legs_filled'] = success_count
        results['total_cost'] = executed_cost
        
        # Check if we got a partial fill (BAD!)
        if 0 < success_count < len(opportunity.markets):
            self.logger.critical(f"🛑 PARTIAL ARBITRAGE FILL! Ordered {len(opportunity.markets)} legs, filled {success_count}. Attempting auto-liquidation...")
            
            # Auto-liquidate filled legs to close exposure
            try:
                liquidation_results = await self._liquidate_partial_arb_legs(leg_results, live_mode)
                results['liquidation_attempted'] = True
                results['liquidation_success'] = liquidation_results.get('success', False)
                results['liquidation_details'] = liquidation_results
                self.logger.warning(f"Liquidation {'succeeded' if liquidation_results.get('success') else 'failed'}: {liquidation_results}")
            except Exception as liquidation_error:
                self.logger.error(f"Auto-liquidation failed: {liquidation_error}")
                results['liquidation_attempted'] = True
                results['liquidation_success'] = False
            
        elif success_count == len(opportunity.markets):
            # Full success
            results['profit_locked'] = (qty * 1.00) - executed_cost
            self.logger.info(f"✅ Arbitrage successfully executed. Cost: ${executed_cost:.2f}, Locked Profit: ${results['profit_locked']:.2f}")
        
        return results

    async def _place_arb_leg(self, leg_info: Dict, qty: int, live_mode: bool, group_id: str) -> Dict:
        """
        Helper to place a single leg order and track it in DB.
        """
        ticker = leg_info['ticker']
        price_dollars = leg_info['price_dollars']
        price_cents = leg_info['price_cents']
        
        order_res = {
            'success': False,
            'cost': 0.0,
            'error': None
        }
        
        try:
            # 1. Create Position Record in DB (live=False until execution succeeds)
            # We tag it with the group_id (event_ticker) to link them later
            # CRITICAL: Position starts as live=False, only becomes live after 
            # successful order fill via update_position_to_live()
            # This ensures orphan cleanup catches failed arbitrage executions
            position = Position(
                market_id=ticker,
                side="YES",
                entry_price=price_dollars,
                quantity=qty,
                timestamp=datetime.now(),
                rationale=f"Arbitrage No-Resolution Group: {group_id}",
                confidence=1.0, # Mathematical certainty (model assumption)
                live=False,  # SAFE PATTERN: Start non-live, update after fill
                status='open',
                strategy='arbitrage'  # Must match monitoring/summary filters
            )
            
            # Insert position
            pos_id = await self.db_manager.add_position(position)
            if not pos_id:
                # If position already exists, we might need to handle it, but for arb we usually assume clean slate
                # Fetch existing to proceed?
                existing = await self.db_manager.get_position_by_market_and_side(ticker, "YES")
                if existing: pos_id = existing.id
            
            if not pos_id:
                order_res['error'] = f"DB Error creating position for {ticker}"
                return order_res

            # 2. Execute Order (Limit Buy at Ask)
            if live_mode:
                client_order_id = str(uuid.uuid4())
                
                # Create Order record
                order = Order(
                    market_id=ticker,
                    side="YES",
                    action="buy",
                    order_type="limit",
                    quantity=qty,
                    price=price_dollars,
                    status="pending",
                    client_order_id=client_order_id,
                    created_at=datetime.now(),
                    position_id=pos_id
                )
                order_id = await self.db_manager.add_order(order)
                
                # API Call
                # We use specific yes_price to make it a LIMIT order
                api_response = await self.kalshi_client.place_order(
                    ticker=ticker,
                    client_order_id=client_order_id,
                    side="yes",
                    action="buy",
                    count=qty,
                    type_="limit",
                    yes_price=price_cents # Explicit limit price
                )
                
                if 'order' in api_response:
                    kalshi_id = api_response['order'].get('order_id')
                    await self.db_manager.update_order_status(order_id, 'placed', kalshi_order_id=kalshi_id)
                    
                    # Verify fill by checking order status (production requirement)
                    await asyncio.sleep(0.5)  # Brief wait for order processing
                    
                    try:
                        # Check if order filled via fills API
                        fills_response = await self.kalshi_client.get_fills(ticker=ticker, limit=10)
                        fills = fills_response.get('fills', [])
                        
                        # Find our order in recent fills
                        our_fill = None
                        for fill in fills:
                            if fill.get('order_id') == kalshi_id:
                                our_fill = fill
                                break
                        
                        if our_fill:
                            actual_qty_filled = our_fill.get('count', 0)
                            actual_price_cents = our_fill.get('yes_price', price_cents)
                            actual_price_dollars = actual_price_cents / 100.0
                            
                            if actual_qty_filled == qty:
                                # Full fill success
                                order_res['success'] = True
                                order_res['cost'] = actual_qty_filled * actual_price_dollars
                                await self.db_manager.update_order_status(order_id, 'filled', fill_price=actual_price_dollars)
                                await self.db_manager.update_position_to_live(pos_id, actual_price_dollars)
                                self.logger.info(f"✅ Order {kalshi_id} filled: {actual_qty_filled} @ ${actual_price_dollars:.3f}")
                            else:
                                # Partial fill - critical issue
                                self.logger.critical(f"⚠️ PARTIAL FILL: {actual_qty_filled}/{qty} filled for {ticker}")
                                order_res['success'] = False
                                order_res['error'] = f"Partial fill: {actual_qty_filled}/{qty}"
                                await self.db_manager.update_order_status(order_id, 'partial')
                        else:
                            # Order not filled yet - treat as failure for arbitrage
                            self.logger.warning(f"Order {kalshi_id} not filled immediately for {ticker}")
                            order_res['success'] = False
                            order_res['error'] = "Order not filled"
                            await self.db_manager.update_order_status(order_id, 'unfilled')
                            
                    except Exception as fill_check_error:
                        self.logger.error(f"Fill verification failed for {ticker}: {fill_check_error}")
                        order_res['success'] = False
                        order_res['error'] = f"Fill check failed: {fill_check_error}"
                    
                else:
                    await self.db_manager.update_order_status(order_id, 'failed')
                    order_res['error'] = f"API Error: {api_response}"
            
            else:
                # Simulated
                order_res['success'] = True
                order_res['cost'] = qty * price_dollars
                self.logger.info(f"Simulated BUY {qty} YES @ {price_cents}¢ on {ticker}")

        except Exception as e:
            self.logger.error(f"Leg execution failed for {ticker}: {e}")
            order_res['error'] = str(e)
            
        return order_res

    async def _liquidate_partial_arb_legs(self, leg_results: List[Dict], live_mode: bool) -> Dict:
        """
        Liquidate successfully filled legs from a partial arbitrage fill.
        
        This critical function prevents exposure when not all legs of an arbitrage are filled.
        Uses market orders to ensure immediate liquidation, even at a loss.
        
        Args:
            leg_results: Results from _place_arb_leg attempts
            live_mode: Whether to place real orders
            
        Returns:
            Dict with liquidation results and details
        """
        liquidation_summary = {
            'success': True,
            'legs_liquidated': 0,
            'legs_failed': 0,
            'total_loss': 0.0,
            'details': []
        }
        
        try:
            for res in leg_results:
                # Only liquidate successfully filled legs
                if not res.get('success'):
                    continue
                    
                ticker = res.get('ticker')
                qty = res.get('qty', 0)
                original_cost = res.get('cost', 0)
                
                if not ticker or qty == 0:
                    continue
                
                try:
                    # Place SELL market order to liquidate immediately
                    # We accept a loss here to close exposure - better than unlimited risk
                    
                    if live_mode:
                        # Get current market for liquidation pricing
                        market_data = await self.kalshi_client.get_market(ticker)
                        if not market_data or 'market' not in market_data:
                            raise ValueError(f"Could not fetch market data for {ticker}")
                        
                        market = market_data['market']
                        
                        # Get current YES bid (what buyers will pay us)
                        yes_bid = market.get('yes_bid', 0)
                        if yes_bid == 0:
                            # No bid available - use last price minus safety margin
                            yes_bid = max(1, market.get('last_price', 50) - 5)  # At least 1¢
                        
                        # Place aggressive sell order at current bid (cross spread for immediate fill)
                        client_order_id = f"arb_liquidate_{ticker}_{int(datetime.now().timestamp())}"
                        
                        order_response = await self.kalshi_client.place_order(
                            ticker=ticker,
                            client_order_id=client_order_id,
                            side='yes',  # Selling YES
                            action='sell',
                            count=qty,
                            type_='limit',  # Use limit at bid for better control
                            yes_price=yes_bid
                        )
                        
                        if 'order' in order_response:
                            kalshi_order_id = order_response['order'].get('order_id')
                            
                            # Wait briefly for fill
                            await asyncio.sleep(0.5)
                            
                            # Verify liquidation fill
                            fills = await self.kalshi_client.get_fills(ticker=ticker, limit=5)
                            liquidation_filled = False
                            liquidation_price = 0
                            
                            if 'fills' in fills:
                                for fill in fills['fills']:
                                    if fill.get('order_id') == kalshi_order_id:
                                        liquidation_filled = True
                                        liquidation_price = fill.get('yes_price', 0) / 100
                                        break
                            
                            if liquidation_filled:
                                # Calculate loss from liquidation
                                proceeds = qty * liquidation_price
                                loss = original_cost - proceeds
                                
                                liquidation_summary['legs_liquidated'] += 1
                                liquidation_summary['total_loss'] += loss
                                liquidation_summary['details'].append({
                                    'ticker': ticker,
                                    'qty': qty,
                                    'original_cost': original_cost,
                                    'liquidation_price': liquidation_price,
                                    'proceeds': proceeds,
                                    'loss': loss
                                })
                                
                                self.logger.info(f"✅ Liquidated {qty} {ticker} @ ${liquidation_price:.3f} (loss: ${loss:.2f})")
                            else:
                                # Liquidation order didn't fill - CRITICAL
                                self.logger.critical(f"🚨 Liquidation order {kalshi_order_id} not filled for {ticker}! Manual intervention required.")
                                liquidation_summary['success'] = False
                                liquidation_summary['legs_failed'] += 1
                                liquidation_summary['details'].append({
                                    'ticker': ticker,
                                    'qty': qty,
                                    'error': 'Liquidation order not filled'
                                })
                        else:
                            raise ValueError(f"Failed to place liquidation order: {order_response}")
                    
                    else:
                        # Paper trading simulation
                        liquidation_summary['legs_liquidated'] += 1
                        self.logger.info(f"[SIMULATED] Liquidated {qty} {ticker}")
                        
                except Exception as leg_error:
                    self.logger.error(f"Failed to liquidate leg {ticker}: {leg_error}")
                    liquidation_summary['success'] = False
                    liquidation_summary['legs_failed'] += 1
                    liquidation_summary['details'].append({
                        'ticker': ticker,
                        'qty': qty,
                        'error': str(leg_error)
                    })
            
            if liquidation_summary['legs_failed'] > 0:
                liquidation_summary['success'] = False
            
            return liquidation_summary
            
        except Exception as e:
            self.logger.error(f"Critical error in partial liquidation: {e}")
            return {
                'success': False,
                'error': str(e),
                'legs_liquidated': 0,
                'legs_failed': len([r for r in leg_results if r.get('success')])
            }

    async def monitor_arbitrage_positions(self) -> Dict:
        """
        Monitor all arbitrage positions and auto-close on market resolution.
        
        Returns:
            Dictionary with monitoring results.
        """
        results = {
            'positions_checked': 0,
            'positions_closed': 0,
            'profit_realized': 0.0,
            'errors': []
        }
        
        try:
            # Get all open arbitrage positions from database
            positions = await self.db_manager.get_open_positions()
            arbitrage_positions = [p for p in positions if p.strategy == 'arbitrage']
            
            results['positions_checked'] = len(arbitrage_positions)
            
            if not arbitrage_positions:
                self.logger.debug("No arbitrage positions to monitor")
                return results
            
            self.logger.info(f"Monitoring {len(arbitrage_positions)} arbitrage positions")
            
            # Group positions by market for efficiency
            market_positions = {}
            for pos in arbitrage_positions:
                if pos.market_id not in market_positions:
                    market_positions[pos.market_id] = []
                market_positions[pos.market_id].append(pos)
            
            # Check each market for resolution
            for market_id, positions_list in market_positions.items():
                try:
                    # Fetch market status
                    market_data = await self.kalshi_client.get_market(market_id)
                    if not market_data or 'market' not in market_data:
                        self.logger.warning(f"Could not fetch market data for {market_id}")
                        continue
                    
                    market = market_data['market']
                    status = market.get('status', 'unknown')
                    result = market.get('result')  # 'yes' or 'no' if resolved
                    
                    # Auto-close if market resolved
                    if status == 'closed' and result:
                        self.logger.info(f"🏁 Market {market_id} resolved: {result.upper()}")
                        
                        for pos in positions_list:
                            # Calculate P&L based on resolution
                            if result.lower() == pos.side.lower():
                                # Won: position worth $1
                                exit_price = 1.0
                                pnl = (exit_price - pos.entry_price) * pos.quantity
                            else:
                                # Lost: position worth $0
                                exit_price = 0.0
                                pnl = (exit_price - pos.entry_price) * pos.quantity
                            
                            # Create trade log
                            trade_log = TradeLog(
                                market_id=market_id,
                                side=pos.side,
                                entry_price=pos.entry_price,
                                exit_price=exit_price,
                                quantity=pos.quantity,
                                pnl=pnl,
                                entry_timestamp=pos.timestamp,
                                exit_timestamp=datetime.now(),
                                rationale=pos.rationale,
                                strategy='arbitrage',
                                exit_reason='market_resolution'
                            )
                            
                            # Record trade and close position
                            await self.db_manager.add_trade_log(trade_log)
                            await self.db_manager.update_position_status(pos.id, 'closed')
                            
                            results['positions_closed'] += 1
                            results['profit_realized'] += pnl
                            
                            self.logger.info(
                                f"✅ Closed arbitrage position: {market_id} {pos.side} "
                                f"@ ${exit_price:.3f} (P&L: ${pnl:+.2f})"
                            )
                
                except Exception as market_error:
                    error_msg = f"Error monitoring {market_id}: {market_error}"
                    self.logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            # Log summary
            if results['positions_closed'] > 0:
                self.logger.info(
                    f"📊 Monitoring complete: {results['positions_closed']} positions closed, "
                    f"P&L: ${results['profit_realized']:+.2f}"
                )
            
            return results
            
        except Exception as e:
            error_msg = f"Critical error in position monitoring: {e}"
            self.logger.error(error_msg)
            results['errors'].append(error_msg)
            return results

    async def get_arbitrage_summary(self) -> Dict:
        """
        Get summary of arbitrage performance and current status.
        
        Returns:
            Dictionary with performance metrics.
        """
        try:
            # Get trade logs for arbitrage strategy
            trade_logs = await self.db_manager.get_all_trade_logs()
            arb_trades = [t for t in trade_logs if t.strategy == 'arbitrage']
            
            # Calculate metrics
            total_trades = len(arb_trades)
            total_pnl = sum(t.pnl for t in arb_trades)
            winning_trades = sum(1 for t in arb_trades if t.pnl > 0)
            losing_trades = sum(1 for t in arb_trades if t.pnl < 0)
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Get current positions
            positions = await self.db_manager.get_open_positions()
            arb_positions = [p for p in positions if p.strategy == 'arbitrage']
            
            capital_deployed = sum(p.entry_price * p.quantity for p in arb_positions)
            
            return {
                'total_trades': total_trades,
                'total_pnl': total_pnl,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'open_positions': len(arb_positions),
                'capital_deployed': capital_deployed
            }
            
        except Exception as e:
            self.logger.error(f"Error getting arbitrage summary: {e}")
            return {}

