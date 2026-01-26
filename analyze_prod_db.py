#!/usr/bin/env python3
"""Quick analysis of the production database."""

import sqlite3
from datetime import datetime, timedelta

# Connect to the production database copy
DB_PATH = "/tmp/production_db.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("=" * 60)
    print("PRODUCTION DATABASE ANALYSIS")
    print("=" * 60)
    
    # 1. Open Positions
    print("\n📊 OPEN POSITIONS")
    print("-" * 40)
    cursor = conn.execute("SELECT * FROM positions WHERE status = 'open' ORDER BY timestamp DESC")
    positions = cursor.fetchall()
    print(f"Total open positions: {len(positions)}")
    
    if positions:
        for p in positions[:15]:
            p = dict(p)
            print(f"  • {p['market_id'][:45]}")
            print(f"    Side: {p['side']} | Qty: {p['quantity']} | Entry: ${p['entry_price']:.3f}")
            print(f"    Strategy: {p['strategy']} | Live: {p['live']} | Tracked: {p.get('tracked', 'N/A')}")
    else:
        print("  No open positions")
    
    # 2. Closed/Failed Positions
    print("\n📦 CLOSED/FAILED POSITIONS (Last 20)")
    print("-" * 40)
    cursor = conn.execute("""
        SELECT * FROM positions 
        WHERE status IN ('closed', 'failed') 
        ORDER BY timestamp DESC LIMIT 20
    """)
    closed = cursor.fetchall()
    print(f"Total found: {len(closed)}")
    
    for p in closed[:10]:
        p = dict(p)
        print(f"  • {p['market_id'][:40]} | {p['status']} | {p['side']} @ ${p['entry_price']:.3f}")
    
    # 3. Trade Logs (P&L)
    print("\n💰 TRADE LOGS (Last 7 days)")
    print("-" * 40)
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor = conn.execute("""
        SELECT * FROM trade_logs 
        WHERE exit_timestamp > ? 
        ORDER BY exit_timestamp DESC
    """, (week_ago,))
    trades = cursor.fetchall()
    print(f"Total trades: {len(trades)}")
    
    if trades:
        total_pnl = sum(dict(t)['pnl'] for t in trades)
        wins = sum(1 for t in trades if dict(t)['pnl'] > 0)
        losses = sum(1 for t in trades if dict(t)['pnl'] <= 0)
        print(f"Total P&L: ${total_pnl:.2f}")
        print(f"Wins: {wins} | Losses: {losses}")
        
        print("\nRecent trades:")
        for t in trades[:10]:
            t = dict(t)
            print(f"  • {t['market_id'][:35]} | {t['side']} | PnL: ${t['pnl']:.2f} | {t.get('exit_reason', 'N/A')}")
    else:
        print("  No trades in the last 7 days")
    
    # 4. Daily AI Costs
    print("\n🤖 DAILY AI COSTS (Last 7 days)")
    print("-" * 40)
    cursor = conn.execute("SELECT * FROM daily_cost_tracking ORDER BY date DESC LIMIT 7")
    costs = cursor.fetchall()
    
    total_cost = 0
    for c in costs:
        c = dict(c)
        total_cost += c['total_ai_cost']
        print(f"  {c['date']} | Cost: ${c['total_ai_cost']:.3f} | Analyses: {c['analysis_count']} | Decisions: {c['decision_count']}")
    print(f"  7-day total: ${total_cost:.3f}")
    
    # 5. Market Analyses Summary
    print("\n🔍 MARKET ANALYSES (Last 24h)")
    print("-" * 40)
    day_ago = (datetime.now() - timedelta(days=1)).isoformat()
    cursor = conn.execute("""
        SELECT decision_action, COUNT(*) as cnt, SUM(cost_usd) as total_cost
        FROM market_analyses 
        WHERE analysis_timestamp > ?
        GROUP BY decision_action
    """, (day_ago,))
    analyses = cursor.fetchall()
    
    for a in analyses:
        a = dict(a)
        print(f"  {a['decision_action']}: {a['cnt']} analyses (${a['total_cost']:.3f})")
    
    # 6. LLM Queries
    print("\n🧠 LLM QUERIES (Last 24h)")
    print("-" * 40)
    cursor = conn.execute("""
        SELECT strategy, query_type, COUNT(*) as cnt, SUM(cost_usd) as total_cost
        FROM llm_queries 
        WHERE timestamp > ?
        GROUP BY strategy, query_type
        ORDER BY cnt DESC
    """, (day_ago,))
    queries = cursor.fetchall()
    
    if queries:
        for q in queries:
            q = dict(q)
            cost = q['total_cost'] or 0
            print(f"  {q['strategy']} / {q['query_type']}: {q['cnt']} queries (${cost:.3f})")
    else:
        print("  No LLM queries in the last 24h")
    
    # 7. Orders
    print("\n📋 RECENT ORDERS")
    print("-" * 40)
    cursor = conn.execute("""
        SELECT * FROM orders ORDER BY created_at DESC LIMIT 10
    """)
    orders = cursor.fetchall()
    print(f"Total recent orders: {len(orders)}")
    
    for o in orders[:5]:
        o = dict(o)
        print(f"  • {o['market_id'][:35]} | {o['action']} {o['side']} | {o['status']}")
    
    # 8. Balance History
    print("\n💵 BALANCE HISTORY (Last 5 snapshots)")
    print("-" * 40)
    cursor = conn.execute("""
        SELECT * FROM balance_history ORDER BY timestamp DESC LIMIT 5
    """)
    balances = cursor.fetchall()
    
    for b in balances:
        b = dict(b)
        print(f"  {b['timestamp'][:19]} | Cash: ${b['cash_balance']:.2f} | Positions: ${b['position_value']:.2f} | Total: ${b['total_value']:.2f}")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
