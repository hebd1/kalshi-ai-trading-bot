#!/usr/bin/env python3
"""Check and optionally liquidate Kalshi positions."""
import asyncio
import sys
sys.path.insert(0, '/app')

from src.config.settings import settings
settings.api.configure_environment(use_live=True)
from src.clients.kalshi_client import KalshiClient

async def main():
    client = KalshiClient()
    
    # Get balance
    balance = await client.get_balance()
    print('=== KALSHI ACCOUNT STATUS ===')
    print(f"Balance: ${balance.get('balance', 0) / 100:.2f}")
    print(f"Portfolio Value: ${balance.get('portfolio_value', 0) / 100:.2f}")
    
    # Get positions
    positions = await client.get_positions()
    market_positions = positions.get('market_positions', [])
    
    active = [p for p in market_positions if p.get('position', 0) != 0]
    print(f'\n=== ACTIVE KALSHI POSITIONS ({len(active)}) ===')
    
    total_value = 0
    for p in active:
        ticker = p.get('ticker', 'unknown')
        position = p.get('position', 0)
        side = 'YES' if position > 0 else 'NO'
        qty = abs(position)
        # Get market data for current price
        try:
            market = await client.get_market(ticker)
            market_data = market.get('market', {})
            if side == 'YES':
                current_price = market_data.get('yes_bid', 0) / 100
            else:
                current_price = market_data.get('no_bid', 0) / 100
            value = qty * current_price
            total_value += value
            print(f'  {ticker}')
            print(f'    Side: {side} | Qty: {qty} | Current Bid: ${current_price:.2f} | Value: ${value:.2f}')
        except Exception as e:
            print(f'  {ticker} | {side} | qty={qty} | Error getting price: {e}')
    
    print(f'\nTotal Position Value (at bid): ${total_value:.2f}')
    
    await client.close()

if __name__ == '__main__':
    asyncio.run(main())
