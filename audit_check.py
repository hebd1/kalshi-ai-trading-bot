"""Quick audit check script"""
import asyncio
import json
from src.utils.database import DatabaseManager

async def check():
    db = DatabaseManager()
    await db.initialize()
    
    # Get performance by strategy
    perf = await db.get_performance_by_strategy()
    print('=== STRATEGY PERFORMANCE ===')
    print(json.dumps(perf, indent=2))
    
    # Get open positions
    positions = await db.get_open_positions()
    print(f'\n=== OPEN POSITIONS: {len(positions)} ===')
    for pos in positions[:5]:  # Show first 5
        print(f"  {pos.market_id}: {pos.side} {pos.quantity} @ ${pos.entry_price:.2f}")
    
    # Get daily AI cost
    cost = await db.get_daily_ai_cost()
    print(f'\n=== DAILY AI COST: ${cost:.2f} ===')
    
    # Get trade logs
    logs = await db.get_all_trade_logs()
    print(f'\n=== TRADE LOGS: {len(logs)} total trades ===')
    if logs:
        winning = sum(1 for log in logs if log.pnl > 0)
        losing = sum(1 for log in logs if log.pnl <= 0)
        total_pnl = sum(log.pnl for log in logs)
        print(f"  Winning trades: {winning}")
        print(f"  Losing trades: {losing}")
        print(f"  Win rate: {winning/len(logs)*100:.1f}%")
        print(f"  Total P&L: ${total_pnl:.2f}")

if __name__ == "__main__":
    asyncio.run(check())
