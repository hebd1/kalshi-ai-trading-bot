#!/usr/bin/env python3
"""
Test the infinite sync loop fix.

This tests that has_any_position_for_market_and_side() correctly detects
closed positions, preventing the infinite sync loop bug.
"""

import asyncio
import tempfile
import os
from src.utils.database import DatabaseManager, Position
from datetime import datetime

async def test_fix():
    print("=== TESTING INFINITE SYNC LOOP FIX ===")
    
    # Use temp file database (in-memory doesn't persist tables properly)
    temp_db = tempfile.mktemp(suffix=".db")
    db = DatabaseManager(temp_db)
    
    try:
        await db.initialize()
        
        # Create a position
        pos = Position(
            market_id="TEST-MARKET",
            side="YES",
            entry_price=0.50,
            quantity=10,
            timestamp=datetime.now(),
            rationale="Test",
            strategy="sync_recovery",
            status="open"
        )
        pos_id = await db.add_position(pos)
        print(f"✅ Created test position (id={pos_id})")
        
        # Check: open position exists
        open_pos = await db.get_position_by_market_and_side("TEST-MARKET", "YES")
        print(f"✅ get_position_by_market_and_side (open): Found={open_pos is not None}")
        
        # Check: has_any_position returns True
        has_any = await db.has_any_position_for_market_and_side("TEST-MARKET", "YES")
        print(f"✅ has_any_position_for_market_and_side (open): {has_any}")
        
        # Close the position (simulating stop-loss)
        await db.update_position_status(pos_id, "closed")
        print(f"✅ Closed position (simulating stop-loss)")
        
        # Check: open position should NOT be found
        open_pos = await db.get_position_by_market_and_side("TEST-MARKET", "YES")
        print(f"✅ get_position_by_market_and_side (closed): Found={open_pos is not None}")
        
        # Check: has_any should STILL return True (THE FIX!)
        has_any = await db.has_any_position_for_market_and_side("TEST-MARKET", "YES")
        print(f"✅ has_any_position_for_market_and_side (closed): {has_any}")
        
        print()
        if has_any:
            print("🎉 FIX VERIFIED! Closed positions are detected, preventing infinite sync loop.")
            return True
        else:
            print("❌ FIX FAILED! Closed positions not detected.")
            return False
    
    finally:
        # Cleanup temp database file
        if os.path.exists(temp_db):
            os.remove(temp_db)

if __name__ == "__main__":
    result = asyncio.run(test_fix())
    exit(0 if result else 1)
