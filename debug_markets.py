#!/usr/bin/env python3
"""Quick debug script to check why no markets are eligible."""

import asyncio
import aiosqlite
from datetime import datetime

async def check_markets():
    db_path = 'trading_system.db'
    
    async with aiosqlite.connect(db_path) as db:
        # Check total market count
        cursor = await db.execute('SELECT COUNT(*) FROM markets')
        total = (await cursor.fetchone())[0]
        print(f'Total markets in DB: {total}')
        
        # Check active market count
        cursor = await db.execute("SELECT COUNT(*) FROM markets WHERE status = 'active'")
        active = (await cursor.fetchone())[0]
        print(f'Active markets: {active}')
        
        # Check volume distribution
        cursor = await db.execute("SELECT MIN(volume), AVG(volume), MAX(volume) FROM markets WHERE status = 'active'")
        row = await cursor.fetchone()
        if row[0] is not None:
            print(f'Volume - Min: {row[0]}, Avg: {row[1]:.0f}, Max: {row[2]}')
        else:
            print('No active markets with volume data')
        
        # Check how many markets have volume >= 200
        cursor = await db.execute("SELECT COUNT(*) FROM markets WHERE status = 'active' AND volume >= 200")
        vol200 = (await cursor.fetchone())[0]
        print(f'Markets with volume >= 200: {vol200}')
        
        # Check how many markets have has_position = 0
        cursor = await db.execute("SELECT COUNT(*) FROM markets WHERE status = 'active' AND has_position = 0")
        no_pos = (await cursor.fetchone())[0]
        print(f'Markets without positions (has_position=0): {no_pos}')
        
        # Check expiration - how many are not expired
        now_ts = int(datetime.now().timestamp())
        max_expiry = now_ts + (365 * 24 * 60 * 60)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM markets WHERE status = 'active' AND expiration_ts > ? AND expiration_ts <= ?", 
            (now_ts, max_expiry)
        )
        not_expired = (await cursor.fetchone())[0]
        print(f'Markets not expired (within 365 days): {not_expired}')
        
        # The actual query used by get_eligible_markets
        cursor = await db.execute('''
            SELECT COUNT(*) FROM markets
            WHERE volume >= 200
            AND expiration_ts > ?
            AND expiration_ts <= ?
            AND status = 'active'
            AND has_position = 0
        ''', (now_ts, max_expiry))
        eligible = (await cursor.fetchone())[0]
        print(f'\n>>> ELIGIBLE MARKETS (volume>=200, not expired, no position): {eligible}')
        
        # Show sample markets that meet criteria
        cursor = await db.execute('''
            SELECT market_id, title, volume, has_position, status FROM markets
            WHERE volume >= 200
            AND expiration_ts > ?
            AND expiration_ts <= ?
            AND status = 'active'
            AND has_position = 0
            LIMIT 5
        ''', (now_ts, max_expiry))
        rows = await cursor.fetchall()
        print(f'\nSample eligible markets:')
        for row in rows:
            market_id = row[0][:30] if row[0] else 'N/A'
            print(f'  {market_id}: vol={row[2]}, has_pos={row[3]}, status={row[4]}')
        
        # Check if has_position might be the issue
        cursor = await db.execute('''
            SELECT COUNT(*) FROM markets
            WHERE volume >= 200
            AND expiration_ts > ?
            AND expiration_ts <= ?
            AND status = 'active'
        ''', (now_ts, max_expiry))
        without_pos_check = (await cursor.fetchone())[0]
        print(f'\nMarkets meeting criteria WITHOUT has_position check: {without_pos_check}')

if __name__ == '__main__':
    asyncio.run(check_markets())
