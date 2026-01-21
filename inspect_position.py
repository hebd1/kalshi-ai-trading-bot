
import asyncio
from src.utils.database import DatabaseManager

async def analyze_position():
    db = DatabaseManager()
    await db.initialize()
    
    # Get the specific position
    pos = await db.get_position_by_market_id('KXAOWOMEN-26-MKEY')
    
    if pos:
        print(f"--- Position Details ---")
        print(f"Market ID: {pos.market_id}")
        print(f"Side: {pos.side}")
        print(f"Quantity: {pos.quantity}")
        print(f"Entry Price: {pos.entry_price}")
        print(f"Rationale: {pos.rationale}")
        print(f"Strategy: {pos.strategy}")
        print(f"Timestamp: {pos.timestamp}")
    else:
        print("Position not found in 'open' status. Checking closed positions...")
        
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM positions WHERE market_id = ?", ('KXAOWOMEN-26-MKEY',))
            rows = await cursor.fetchall()
            for row in rows:
                print(f"--- Position Record (Status: {row['status']}) ---")
                print(f"Rationale: {row['rationale']}")
                print(f"Strategy: {row['strategy']}")
                print(f"Quantity: {row['quantity']}")
                print(f"Timestamp: {row['timestamp']}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(analyze_position())
