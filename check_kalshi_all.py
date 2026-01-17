#!/usr/bin/env python3
"""Check ALL Kalshi positions including zero positions."""

import asyncio
from src.clients.kalshi_client import KalshiClient


async def main():
    """Check all Kalshi positions."""
    kalshi = KalshiClient()
    
    response = await kalshi.get_positions()
    all_positions = response.get('market_positions', [])
    
    print(f"\n📊 ALL KALSHI POSITIONS ({len(all_positions)} total)")
    print("=" * 80)
    
    active_count = 0
    zero_count = 0
    
    for i, p in enumerate(all_positions, 1):
        ticker = p.get('ticker')
        position = p.get('position', 0)
        
        if position == 0:
            status_emoji = "⭕"
            zero_count += 1
        else:
            status_emoji = "✅"
            active_count += 1
            
        side = "YES" if position > 0 else "NO" if position < 0 else "NONE"
        
        print(f"{i}. {status_emoji} {ticker}")
        print(f"   Position: {position} contracts ({side})")
        print(f"   Resting orders: {p.get('resting_order_count', 0)}")
        print(f"   Total traded: {p.get('total_traded', 0)}")
        print()
    
    print("=" * 80)
    print(f"Summary: {active_count} active positions, {zero_count} with zero position")
    print()
    
    await kalshi.close()


if __name__ == "__main__":
    asyncio.run(main())
