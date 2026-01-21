#!/usr/bin/env python3
"""
Liquidate All Production Positions

This script will:
1. Check all open positions in production
2. Display a summary of what will be liquidated
3. Ask for confirmation
4. Place market sell orders for all positions
5. Update the database to reflect the liquidation

⚠️  WARNING: This will liquidate ALL positions immediately at market prices!
"""

import asyncio
import sys
from datetime import datetime
from typing import List, Dict

sys.path.append('.')

from src.clients.kalshi_client import KalshiClient
from src.utils.database import DatabaseManager, TradeLog
from src.config.settings import settings


async def get_current_positions(kalshi_client: KalshiClient) -> List[Dict]:
    """Get all non-zero positions from Kalshi."""
    response = await kalshi_client.get_positions()
    positions = response.get('market_positions', [])
    
    # Filter to only positions with non-zero holdings
    active_positions = []
    for pos in positions:
        position_count = pos.get('position', 0)
        if position_count != 0:
            ticker = pos.get('ticker')
            side = 'YES' if position_count > 0 else 'NO'
            quantity = abs(position_count)
            
            # Get current market data for P&L calculation
            try:
                market_data = await kalshi_client.get_market(ticker)
                market_info = market_data.get('market', {})
                
                if side == 'YES':
                    current_price = (market_info.get('yes_bid', 0) or 
                                   market_info.get('last_price', 50)) / 100
                else:
                    current_price = (market_info.get('no_bid', 0) or 
                                   (100 - market_info.get('last_price', 50))) / 100
                
                active_positions.append({
                    'ticker': ticker,
                    'side': side,
                    'quantity': quantity,
                    'current_price': current_price,
                    'market_info': market_info
                })
            except Exception as e:
                print(f"⚠️  Warning: Could not get market data for {ticker}: {e}")
                active_positions.append({
                    'ticker': ticker,
                    'side': side,
                    'quantity': quantity,
                    'current_price': 0.50,  # Fallback
                    'market_info': {}
                })
    
    return active_positions


async def display_liquidation_summary(positions: List[Dict], db_manager: DatabaseManager):
    """Display what will be liquidated."""
    print("\n" + "=" * 80)
    print("🚨 LIQUIDATION SUMMARY - PRODUCTION POSITIONS")
    print("=" * 80)
    print(f"\nFound {len(positions)} active position(s) to liquidate:\n")
    
    total_value = 0.0
    total_unrealized_pnl = 0.0
    
    for i, pos in enumerate(positions, 1):
        ticker = pos['ticker']
        side = pos['side']
        quantity = pos['quantity']
        current_price = pos['current_price']
        
        # Try to get entry price from database
        db_position = await db_manager.get_position_by_market_and_side(ticker, side)
        if db_position:
            entry_price = db_position.entry_price
            unrealized_pnl = (current_price - entry_price) * quantity
            pnl_percent = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            pnl_indicator = "🟢" if unrealized_pnl > 0 else "🔴" if unrealized_pnl < 0 else "⚪"
            
            print(f"{i}. {ticker}")
            print(f"   Side: {side}")
            print(f"   Quantity: {quantity} contracts")
            print(f"   Entry: ${entry_price:.2f} → Current: ${current_price:.2f}")
            print(f"   {pnl_indicator} Unrealized P&L: ${unrealized_pnl:+.2f} ({pnl_percent:+.1f}%)")
            print(f"   Liquidation Value: ${current_price * quantity:.2f}")
        else:
            print(f"{i}. {ticker}")
            print(f"   Side: {side}")
            print(f"   Quantity: {quantity} contracts")
            print(f"   Current: ${current_price:.2f}")
            print(f"   Liquidation Value: ${current_price * quantity:.2f}")
            print(f"   ⚠️  No database entry found (untracked position)")
        
        total_value += current_price * quantity
        if db_position:
            total_unrealized_pnl += (current_price - db_position.entry_price) * quantity
        
        print()
    
    print("-" * 80)
    print(f"Total Liquidation Value: ${total_value:.2f}")
    if total_unrealized_pnl != 0:
        pnl_indicator = "🟢" if total_unrealized_pnl > 0 else "🔴"
        print(f"{pnl_indicator} Total Unrealized P&L: ${total_unrealized_pnl:+.2f}")
    print("=" * 80)


async def liquidate_position(
    pos: Dict, 
    kalshi_client: KalshiClient,
    db_manager: DatabaseManager,
    dry_run: bool = False
) -> bool:
    """Liquidate a single position."""
    ticker = pos['ticker']
    side = pos['side']
    quantity = pos['quantity']
    
    try:
        if dry_run:
            print(f"   [DRY RUN] Would liquidate {quantity} {side} contracts of {ticker}")
            return True
        
        # Place market sell order
        import uuid
        client_order_id = str(uuid.uuid4())
        
        # Get current market data for limit price (market orders need a price parameter)
        market_data = await kalshi_client.get_market(ticker)
        market_info = market_data.get('market', {})
        
        if side == 'YES':
            # Selling YES - use yes_bid or last_price
            price_cents = market_info.get('yes_bid', 0) or market_info.get('last_price', 50)
        else:
            # Selling NO - use no_bid or (100 - last_price)
            price_cents = market_info.get('no_bid', 0) or (100 - market_info.get('last_price', 50))
        
        print(f"   Placing market sell order: {quantity} {side} @ {price_cents}¢")
        
        order_params = {
            "ticker": ticker,
            "client_order_id": client_order_id,
            "side": side.lower(),
            "action": "sell",
            "count": quantity,
            "type_": "market"
        }
        
        # Add price parameter based on side
        if side.lower() == "yes":
            order_params["yes_price"] = price_cents
        else:
            order_params["no_price"] = price_cents
        
        response = await kalshi_client.place_order(**order_params)
        
        if response and 'order' in response:
            print(f"   ✅ Sell order placed: {response['order'].get('order_id', 'unknown')}")
            
            # Update database - close the position and create trade log
            db_position = await db_manager.get_position_by_market_and_side(ticker, side)
            if db_position:
                exit_price = price_cents / 100
                pnl = (exit_price - db_position.entry_price) * quantity
                
                # Create trade log
                trade_log = TradeLog(
                    market_id=ticker,
                    side=side,
                    entry_price=db_position.entry_price,
                    exit_price=exit_price,
                    quantity=quantity,
                    pnl=pnl,
                    entry_timestamp=db_position.timestamp,
                    exit_timestamp=datetime.now(),
                    rationale=db_position.rationale or "Manual liquidation",
                    strategy=db_position.strategy or "manual_liquidation",
                    exit_reason="manual_liquidation",
                    slippage=None
                )
                
                await db_manager.add_trade_log(trade_log)
                await db_manager.update_position_status(db_position.id, 'closed')
                print(f"   📊 Database updated: P&L ${pnl:+.2f}")
            
            return True
        else:
            print(f"   ❌ Failed to place order: {response}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error liquidating {ticker}: {e}")
        return False


async def main():
    """Main liquidation process."""
    print("\n🚨 PRODUCTION POSITION LIQUIDATION TOOL 🚨")
    print("\nThis tool will liquidate ALL positions in your production account.")
    print("⚠️  WARNING: This operation cannot be undone!")
    
    # Configure for production
    settings.api.configure_environment(use_live=True)
    
    kalshi_client = KalshiClient()
    db_manager = DatabaseManager()
    await db_manager.initialize()
    
    try:
        # Step 1: Get current positions
        print("\n📊 Fetching current positions from Kalshi...")
        positions = await get_current_positions(kalshi_client)
        
        if not positions:
            print("\n✅ No active positions found. Nothing to liquidate!")
            return
        
        # Step 2: Display summary
        await display_liquidation_summary(positions, db_manager)
        
        # Step 3: Get confirmation
        print("\n⚠️  Are you ABSOLUTELY SURE you want to liquidate ALL positions?")
        print("This will:")
        print("  - Place MARKET SELL orders for all positions")
        print("  - Close positions at current market prices (potential slippage)")
        print("  - Update the database to reflect the liquidation")
        print("\nType 'LIQUIDATE' to confirm, or anything else to cancel: ", end='')
        
        confirmation = input().strip()
        
        if confirmation != 'LIQUIDATE':
            print("\n❌ Liquidation cancelled. No positions were touched.")
            return
        
        # Step 4: Execute liquidation
        print("\n🔄 Starting liquidation process...")
        print("=" * 80)
        
        success_count = 0
        fail_count = 0
        
        for i, pos in enumerate(positions, 1):
            print(f"\n[{i}/{len(positions)}] Liquidating {pos['ticker']} ({pos['side']})...")
            
            success = await liquidate_position(pos, kalshi_client, db_manager, dry_run=False)
            
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            # Add a small delay between orders to avoid rate limiting
            if i < len(positions):
                await asyncio.sleep(0.5)
        
        # Step 5: Final summary
        print("\n" + "=" * 80)
        print("🏁 LIQUIDATION COMPLETE")
        print("=" * 80)
        print(f"\n✅ Successfully liquidated: {success_count}")
        print(f"❌ Failed to liquidate: {fail_count}")
        
        # Get updated balance
        balance_response = await kalshi_client.get_balance()
        new_balance = balance_response.get('balance', 0) / 100
        print(f"\n💰 Current Cash Balance: ${new_balance:.2f}")
        
        # Verify all positions are closed
        print("\n🔍 Verifying liquidation...")
        remaining_positions = await get_current_positions(kalshi_client)
        if remaining_positions:
            print(f"⚠️  WARNING: {len(remaining_positions)} position(s) still open!")
            for pos in remaining_positions:
                print(f"   - {pos['ticker']} {pos['side']} {pos['quantity']}")
        else:
            print("✅ All positions successfully liquidated!")
        
        print("\n✨ You can now start fresh with a clean slate!")
        
    finally:
        await kalshi_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Liquidation cancelled by user (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
