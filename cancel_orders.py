#!/usr/bin/env python3
"""
Cancel resting orders for a specific ticker

Usage: python cancel_orders.py <TICKER>
Example: python cancel_orders.py KXAOWOMEN-26-MKEY
"""

import asyncio
import sys
import argparse

from src.clients.kalshi_client import KalshiClient
from src.config.settings import settings

async def cancel_orders(ticker: str):
    # Force live environment
    settings.api.configure_environment(use_live=True)
    
    client = KalshiClient()
    try:
        print(f"Checking orders for {ticker}...")
        response = await client.get_orders(ticker=ticker)
        
        orders = response.get('orders', [])
        resting_orders = [o for o in orders if o.get('status') == 'resting']
        
        print(f"Found {len(resting_orders)} resting orders to cancel.")
        
        for order in resting_orders:
            order_id = order.get('order_id')
            print(f"Cancelling order {order_id} ({order.get('side')} - {order.get('remaining_count')} remaining)...")
            try:
                await client.cancel_order(order_id)
                print(f"✅ Cancelled order {order_id}")
            except Exception as e:
                print(f"❌ Failed to cancel order {order_id}: {e}")
                
    finally:
        await client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cancel resting orders for a Kalshi market')
    parser.add_argument('ticker', type=str, help='Market Ticker (e.g., KXAOWOMEN-26-MKEY)')
    args = parser.parse_args()
    
    asyncio.run(cancel_orders(args.ticker))
