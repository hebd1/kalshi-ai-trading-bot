#!/usr/bin/env python3
"""
Liquidate a Specific Position

Usage: python liquidate_single_position.py <TICKER>
Example: python liquidate_single_position.py KXAOWOMEN-26-MKEY
"""

import asyncio
import sys
import argparse
import uuid
from datetime import datetime

from src.clients.kalshi_client import KalshiClient
from src.utils.database import DatabaseManager, TradeLog
from src.config.settings import settings

async def liquidate_position(ticker: str):
    # Force live environment for liquidation
    settings.api.configure_environment(use_live=True)
    
    print(f"🚀 Initializing liquidation for {ticker}...")
    
    db = DatabaseManager()
    await db.initialize()
    
    client = KalshiClient()
    
    try:
        # 1. Verify position on Kalshi (Source of Truth)
        print("📊 Fetching live position from Kalshi...")
        response = await client.get_positions()
        positions = response.get('market_positions', [])
        
        target_pos = next((p for p in positions if p.get('ticker') == ticker), None)
        
        if not target_pos:
            print(f"❌ No open position found on Kalshi for {ticker}")
            return
            
        position_count = target_pos.get('position', 0)
        if position_count == 0:
            print(f"❌ Position is 0 for {ticker}")
            return

        side = 'YES' if position_count > 0 else 'NO'
        quantity = abs(position_count)
        
        print(f"✅ Found Position: {quantity} contracts of {side}")
        
        # 2. Confirm
        confirm = input(f"⚠️  Are you sure you want to SELL ALL {quantity} {side} contracts for {ticker} at MARKET price? (y/n): ")
        if confirm.lower() != 'y':
            print("🚫 Cancelled.")
            return

        # 3. Place Market Sell Order
        print(f"💸 Placing Market Sell Order...")
        client_order_id = str(uuid.uuid4())
        
        # Note: Kalshi requires a price even for market orders (as a safeguard/worst case)
        # For selling YES, safe limit is 1 cent. For selling NO, safe limit is 1 cent.
        # However, to ensure execution we usually send a "Market" type order.
        
        order_params = {
            "ticker": ticker,
            "client_order_id": client_order_id,
            "side": side.lower(), # yes/no
            "action": "sell",     # closing the position
            "count": quantity,
            "type_": "market"
        }
        
        # Add dummy price params required by some API versions even for market orders
        if side == 'YES':
            order_params["yes_price"] = 1 # Sell down to 1 cent
        else:
            order_params["no_price"] = 1  # Sell down to 1 cent

        order_response = await client.place_order(**order_params)
        
        if order_response:
             print(f"✅ Order Placed! ID: {order_response.get('order', {}).get('order_id')}")
        
        # 4. Update Database
        print("💾 Updating Database...")
        db_pos = await db.get_position_by_market_id(ticker)
        if db_pos and db_pos.status == 'open':
            await db.update_position_status(db_pos.id, 'closed')
            
            # Add trade log
            log = TradeLog(
                market_id=ticker,
                side=side,
                entry_price=db_pos.entry_price,
                exit_price=0, # Unknown until fill, assume 0 for log or update later
                quantity=quantity,
                pnl=0, # Unknown
                entry_timestamp=db_pos.timestamp,
                exit_timestamp=datetime.now(),
                rationale="Manual Liquidation Script",
                strategy="manual",
                exit_reason="manual_liquidation"
            )
            await db.add_trade_log(log)
            print("✅ Database updated.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()
        await db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Liquidate a single Kalshi position')
    parser.add_argument('ticker', type=str, help='Market Ticker (e.g., KXAOWOMEN-26-MKEY)')
    args = parser.parse_args()
    
    asyncio.run(liquidate_position(args.ticker))
