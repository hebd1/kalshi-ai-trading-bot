#!/usr/bin/env python3
"""Test script to verify strategy values in dashboard data flow."""

import asyncio
import sys
from src.utils.database import DatabaseManager

async def test_strategy_values():
    """Test the strategy values from database."""
    try:
        print("Starting test...", flush=True)
        db = DatabaseManager()
        print("Database manager created", flush=True)
        await db.initialize()
        print("Database initialized", flush=True)
        
        # Get positions using the same method as dashboard
        positions = await db.get_open_positions()
        print(f"Positions fetched: {len(positions)}", flush=True)
        
        print(f"Total open positions: {len(positions)}", flush=True)
        print(f"\nStrategy distribution:", flush=True)
        
        strategy_counts = {}
        for pos in positions:
            strategy = pos.strategy if pos.strategy else "None"
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        for strategy, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
            print(f"  {strategy}: {count}", flush=True)
        
        # Show first 3 positions in detail
        print(f"\nFirst 3 positions in detail:", flush=True)
        for i, pos in enumerate(positions[:3]):
            print(f"\n  Position {i+1}:", flush=True)
            print(f"    Market: {pos.market_id[:40]}...", flush=True)
            print(f"    Side: {pos.side}", flush=True)
            print(f"    Strategy: {repr(pos.strategy)}", flush=True)
            print(f"    Strategy type: {type(pos.strategy)}", flush=True)
            print(f"    Strategy is None: {pos.strategy is None}", flush=True)
            print(f"    Strategy is falsy: {not pos.strategy}", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_strategy_values())
