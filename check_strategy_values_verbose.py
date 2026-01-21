#!/usr/bin/env python3
"""Check strategy values in database positions - verbose version"""
import asyncio
import aiosqlite
from src.utils.database import DatabaseManager
import sys

async def main():
    db = DatabaseManager()
    print(f"Using database: {db.db_path}")
    await db.initialize()
    
    async with aiosqlite.connect(db.db_path) as conn:
        # Check ALL positions first
        print("\n=== ALL POSITIONS (any status) ===")
        cursor = await conn.execute('SELECT COUNT(*), status FROM positions GROUP BY status')
        rows = await cursor.fetchall()
        if not rows:
            print("  No positions found in database at all!")
            return
        for row in rows:
            print(f"  {row[1]}: {row[0]} positions")
        
        # Check open positions by strategy
        print("\n=== OPEN POSITIONS BY STRATEGY ===")
        cursor = await conn.execute(
            'SELECT COUNT(*) as count, COALESCE(strategy, "NULL") as strat '
            'FROM positions WHERE status="open" GROUP BY strategy ORDER BY count DESC'
        )
        rows = await cursor.fetchall()
        if not rows:
            print("  No open positions found")
        else:
            for row in rows:
                print(f"  {row[1]}: {row[0]} positions")
        
        # Check closed positions by strategy to see historical data
        print("\n=== CLOSED POSITIONS BY STRATEGY ===")
        cursor = await conn.execute(
            'SELECT COUNT(*) as count, COALESCE(strategy, "NULL") as strat '
            'FROM positions WHERE status="closed" GROUP BY strategy ORDER BY count DESC LIMIT 10'
        )
        rows = await cursor.fetchall()
        if not rows:
            print("  No closed positions found")
        else:
            for row in rows:
                print(f"  {row[1]}: {row[0]} positions")
        
        # Show some sample positions
        print("\n=== SAMPLE POSITIONS (first 5) ===")
        cursor = await conn.execute(
            'SELECT id, market_id, side, status, COALESCE(strategy, "NULL") as strat, '
            'rationale FROM positions LIMIT 5'
        )
        rows = await cursor.fetchall()
        for row in rows:
            print(f"  ID={row[0]}: {row[1]} {row[2]} [{row[3]}] strategy={row[4]}")
            print(f"    Rationale: {row[5][:70] if row[5] else 'None'}...")

if __name__ == "__main__":
    asyncio.run(main())
