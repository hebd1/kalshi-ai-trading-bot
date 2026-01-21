import asyncio
import aiosqlite

async def check_schema():
    db = await aiosqlite.connect('trading_system.db')
    cursor = await db.execute('PRAGMA table_info(positions)')
    rows = await cursor.fetchall()
    print("Column index mapping for positions table:")
    for row in rows:
        print(f"  row[{row[0]}] = {row[1]} ({row[2]})")
    await db.close()

asyncio.run(check_schema())
