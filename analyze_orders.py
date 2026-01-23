#!/usr/bin/env python3
"""
Analyze orders from production database to assess success rates.
Excludes manually placed trades (strategy='startup_sync' or 'legacy_untracked').
"""

import asyncio
import aiosqlite
from datetime import datetime, timedelta
from collections import defaultdict

async def analyze_orders():
    """Analyze orders from the production database."""
    
    db_path = "/tmp/production_db.db"
    
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        
        print("=" * 80)
        print("📊 ORDER ANALYSIS - LAST 7 DAYS")
        print("=" * 80)
        
        # Get cutoff time for last 7 days
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        
        # === 1. OVERALL ORDER STATISTICS ===
        print("\n🔍 OVERALL ORDER STATISTICS (Excluding Manual Trades)")
        print("-" * 80)
        
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN o.status = 'filled' THEN 1 ELSE 0 END) as filled,
                SUM(CASE WHEN o.status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN o.status = 'placed' THEN 1 ELSE 0 END) as placed,
                SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
                SUM(CASE WHEN o.status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN o.order_type = 'market' THEN 1 ELSE 0 END) as market_orders,
                SUM(CASE WHEN o.order_type = 'limit' THEN 1 ELSE 0 END) as limit_orders,
                SUM(CASE WHEN o.action = 'buy' THEN 1 ELSE 0 END) as buy_orders,
                SUM(CASE WHEN o.action = 'sell' THEN 1 ELSE 0 END) as sell_orders
            FROM orders o
            LEFT JOIN positions p ON o.position_id = p.id
            WHERE o.created_at >= ?
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
        """, (cutoff,))
        
        row = await cursor.fetchone()
        
        total = row['total_orders']
        if total == 0:
            print("⚠️ No orders found in the last 7 days")
            return
        
        filled = row['filled']
        pending = row['pending']
        placed = row['placed']
        failed = row['failed']
        
        fill_rate = (filled / total * 100) if total > 0 else 0
        
        print(f"Total Orders: {total}")
        print(f"  ✅ Filled: {filled} ({fill_rate:.1f}%)")
        print(f"  ⏳ Pending: {pending}")
        print(f"  📋 Placed: {placed}")
        print(f"  ❌ Failed: {failed}")
        print(f"\nOrder Types:")
        print(f"  📈 Market Orders: {row['market_orders']}")
        print(f"  🎯 Limit Orders: {row['limit_orders']}")
        print(f"\nOrder Actions:")
        print(f"  💰 Buy Orders: {row['buy_orders']}")
        print(f"  💸 Sell Orders: {row['sell_orders']}")
        
        # === 2. ORDER SUCCESS RATE BY STRATEGY ===
        print("\n\n📊 ORDER SUCCESS RATE BY STRATEGY")
        print("-" * 80)
        
        cursor = await db.execute("""
            SELECT 
                COALESCE(p.strategy, 'unknown') as strategy,
                COUNT(*) as total,
                SUM(CASE WHEN o.status = 'filled' THEN 1 ELSE 0 END) as filled,
                SUM(CASE WHEN o.status = 'failed' THEN 1 ELSE 0 END) as failed,
                ROUND(AVG(CASE WHEN o.fill_price IS NOT NULL THEN o.fill_price ELSE 0 END), 3) as avg_fill_price
            FROM orders o
            LEFT JOIN positions p ON o.position_id = p.id
            WHERE o.created_at >= ?
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
            GROUP BY p.strategy
            ORDER BY total DESC
        """, (cutoff,))
        
        rows = await cursor.fetchall()
        
        for row in rows:
            strategy = row['strategy']
            total = row['total']
            filled = row['filled']
            failed = row['failed']
            success_rate = (filled / total * 100) if total > 0 else 0
            
            print(f"\n{strategy}:")
            print(f"  Total: {total} | Filled: {filled} ({success_rate:.1f}%) | Failed: {failed}")
            if row['avg_fill_price'] > 0:
                print(f"  Avg Fill Price: ${row['avg_fill_price']:.3f}")
        
        # === 3. ORDER TYPE PERFORMANCE ===
        print("\n\n🎯 ORDER TYPE PERFORMANCE")
        print("-" * 80)
        
        cursor = await db.execute("""
            SELECT 
                o.order_type,
                COUNT(*) as total,
                SUM(CASE WHEN o.status = 'filled' THEN 1 ELSE 0 END) as filled,
                AVG(CASE 
                    WHEN o.filled_at IS NOT NULL AND o.created_at IS NOT NULL 
                    THEN (julianday(o.filled_at) - julianday(o.created_at)) * 24 * 60 
                    ELSE NULL 
                END) as avg_fill_time_minutes
            FROM orders o
            LEFT JOIN positions p ON o.position_id = p.id
            WHERE o.created_at >= ?
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
            GROUP BY o.order_type
        """, (cutoff,))
        
        rows = await cursor.fetchall()
        
        for row in rows:
            order_type = row['order_type']
            total = row['total']
            filled = row['filled']
            fill_rate = (filled / total * 100) if total > 0 else 0
            avg_fill_time = row['avg_fill_time_minutes']
            
            print(f"\n{order_type.upper()} Orders:")
            print(f"  Total: {total} | Fill Rate: {fill_rate:.1f}%")
            if avg_fill_time:
                print(f"  Avg Fill Time: {avg_fill_time:.1f} minutes")
        
        # === 4. RECENT ORDER ACTIVITY ===
        print("\n\n📅 RECENT ORDER ACTIVITY (Last 24 Hours)")
        print("-" * 80)
        
        recent_cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        
        cursor = await db.execute("""
            SELECT 
                o.created_at,
                o.market_id,
                o.action,
                o.order_type,
                o.status,
                o.quantity,
                o.price,
                o.fill_price,
                COALESCE(p.strategy, 'unknown') as strategy
            FROM orders o
            LEFT JOIN positions p ON o.position_id = p.id
            WHERE o.created_at >= ?
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
            ORDER BY o.created_at DESC
            LIMIT 20
        """, (recent_cutoff,))
        
        rows = await cursor.fetchall()
        
        if rows:
            for row in rows:
                created = datetime.fromisoformat(row['created_at']).strftime('%m-%d %H:%M')
                market = row['market_id'][:30]
                status_emoji = {
                    'filled': '✅',
                    'pending': '⏳',
                    'placed': '📋',
                    'failed': '❌'
                }.get(row['status'], '❓')
                
                print(f"{status_emoji} [{created}] {row['action'].upper()} {row['order_type']} | {market}")
                print(f"   Strategy: {row['strategy']} | Qty: {row['quantity']}", end="")
                if row['price']:
                    print(f" | Price: ${row['price']:.3f}", end="")
                if row['fill_price']:
                    print(f" | Fill: ${row['fill_price']:.3f}", end="")
                print()
        else:
            print("No orders in the last 24 hours")
        
        # === 5. SELL LIMIT ORDER ANALYSIS ===
        print("\n\n💸 SELL LIMIT ORDER ANALYSIS")
        print("-" * 80)
        
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_sell_limits,
                SUM(CASE WHEN o.status = 'filled' THEN 1 ELSE 0 END) as filled,
                SUM(CASE WHEN o.status = 'pending' OR o.status = 'placed' THEN 1 ELSE 0 END) as active,
                AVG(CASE 
                    WHEN o.filled_at IS NOT NULL AND o.created_at IS NOT NULL 
                    THEN (julianday(o.filled_at) - julianday(o.created_at)) * 24 
                    ELSE NULL 
                END) as avg_fill_time_hours
            FROM orders o
            LEFT JOIN positions p ON o.position_id = p.id
            WHERE o.created_at >= ?
            AND o.action = 'sell'
            AND o.order_type = 'limit'
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
        """, (cutoff,))
        
        row = await cursor.fetchone()
        
        if row['total_sell_limits'] > 0:
            total = row['total_sell_limits']
            filled = row['filled']
            active = row['active']
            fill_rate = (filled / total * 100) if total > 0 else 0
            
            print(f"Total Sell Limit Orders: {total}")
            print(f"  ✅ Filled: {filled} ({fill_rate:.1f}%)")
            print(f"  📋 Active: {active}")
            if row['avg_fill_time_hours']:
                print(f"  Avg Fill Time: {row['avg_fill_time_hours']:.1f} hours")
        else:
            print("No sell limit orders in the last 7 days")
        
        # === 6. POSITION-ORDER CORRELATION ===
        print("\n\n🔗 POSITION-ORDER CORRELATION")
        print("-" * 80)
        
        cursor = await db.execute("""
            SELECT 
                COUNT(DISTINCT p.id) as total_positions,
                COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN p.id END) as positions_with_orders,
                COUNT(o.id) as total_orders_for_positions
            FROM positions p
            LEFT JOIN orders o ON o.position_id = p.id
            WHERE p.timestamp >= ?
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
        """, (cutoff,))
        
        row = await cursor.fetchone()
        
        print(f"Positions Created: {row['total_positions']}")
        print(f"Positions with Orders: {row['positions_with_orders']}")
        print(f"Total Orders for Positions: {row['total_orders_for_positions']}")
        
        # === 7. ORDER FILL PRICE ANALYSIS ===
        print("\n\n💰 FILL PRICE ANALYSIS")
        print("-" * 80)
        
        cursor = await db.execute("""
            SELECT 
                COUNT(CASE WHEN o.fill_price IS NOT NULL THEN 1 END) as orders_with_fill_price,
                AVG(CASE WHEN o.fill_price IS NOT NULL THEN ABS(o.fill_price - COALESCE(o.price, o.fill_price)) END) as avg_slippage,
                MIN(o.fill_price) as min_fill,
                MAX(o.fill_price) as max_fill,
                AVG(o.fill_price) as avg_fill
            FROM orders o
            LEFT JOIN positions p ON o.position_id = p.id
            WHERE o.created_at >= ?
            AND o.status = 'filled'
            AND (p.strategy IS NULL OR p.strategy NOT IN ('startup_sync', 'legacy_untracked'))
        """, (cutoff,))
        
        row = await cursor.fetchone()
        
        if row['orders_with_fill_price'] > 0:
            print(f"Orders with Fill Price: {row['orders_with_fill_price']}")
            print(f"Avg Fill Price: ${row['avg_fill']:.3f}")
            print(f"Fill Range: ${row['min_fill']:.3f} - ${row['max_fill']:.3f}")
            if row['avg_slippage']:
                print(f"Avg Slippage: ${row['avg_slippage']:.4f}")
        
        print("\n" + "=" * 80)
        print("✅ Analysis Complete")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(analyze_orders())
