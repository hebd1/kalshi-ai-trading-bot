#!/usr/bin/env python3
"""Check all positions in database including closed ones."""

import asyncio
import aiosqlite


async def main():
    """Check all positions."""
    async with aiosqlite.connect("trading_system.db") as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT market_id, side, quantity, status, timestamp FROM positions ORDER BY timestamp DESC")
        rows = await cursor.fetchall()
        
        print(f"\n📊 ALL POSITIONS IN DATABASE ({len(rows)} total)")
        print("=" * 80)
        
        open_count = 0
        closed_count = 0
        
        for i, row in enumerate(rows, 1):
            status_emoji = "✅" if row[3] == "open" else "❌"
            print(f"{i}. {status_emoji} {row[0]}")
            print(f"   Side: {row[1]}, Quantity: {row[2]}, Status: {row[3]}")
            print(f"   Timestamp: {row[4]}")
            print()
            
            if row[3] == "open":
                open_count += 1
            else:
                closed_count += 1
        
        print("=" * 80)
        print(f"Summary: {open_count} open, {closed_count} closed")
        print()


if __name__ == "__main__":
    asyncio.run(main())
