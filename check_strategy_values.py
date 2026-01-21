#!/usr/bin/env python3
"""Check strategy values in database positions"""
import asyncio
import aiosqlite
from src.utils.database import DatabaseManager

async def main():
    db = DatabaseManager()
    await db.initialize()
    
    async with aiosqlite.connect(db.db_path) as conn:
        # Check open positions by strategy
        print("\n=== OPEN POSITIONS BY STRATEGY ===")
        cursor = await conn.execute(
            'SELECT COUNT(*) as count, COALESCE(strategy, "NULL") as strat '
            'FROM positions WHERE status="open" GROUP BY strategy ORDER BY count DESC'
        )
        rows = await cursor.fetchall()
        for row in rows:
            print(f"  {row[1]}: {row[0]} positions")
        
        # Check total open positions
        cursor = await conn.execute('SELECT COUNT(*) FROM positions WHERE status="open"')
        total = (await cursor.fetchone())[0]
        print(f"\nTotal open positions: {total}")
        
        # Show some sample positions with NULL strategy
        print("\n=== SAMPLE POSITIONS WITH NULL STRATEGY ===")
        cursor = await conn.execute(
            'SELECT market_id, side, rationale FROM positions '
            'WHERE status="open" AND strategy IS NULL LIMIT 5'
        )
        rows = await cursor.fetchall()
        for row in rows:
            print(f"  {row[0]}: {row[1]} - {row[2][:50] if row[2] else 'No rationale'}...")

if __name__ == "__main__":
    asyncio.run(main())
