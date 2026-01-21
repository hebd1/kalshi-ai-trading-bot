#!/usr/bin/env python3
"""Compare performance between original and updated bot versions."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.database import DatabaseManager


async def analyze_bot(db_path: str, name: str):
    """Analyze a bot's performance."""
    print(f"\n{'='*60}")
    print(f"Analyzing {name}")
    print(f"{'='*60}")
    
    db = DatabaseManager(db_path)
    await db.initialize()
    
    # Get trade logs
    logs = await db.get_all_trade_logs()
    
    if not logs:
        print("No trades found")
        return
    
    print(f"\nTotal trades: {len(logs)}")
    
    # Calculate metrics
    winning_trades = [l for l in logs if l.pnl > 0]
    losing_trades = [l for l in logs if l.pnl <= 0]
    
    print(f"Winning trades: {len(winning_trades)} ({len(winning_trades)/len(logs)*100:.1f}%)")
    print(f"Losing trades: {len(losing_trades)} ({len(losing_trades)/len(logs)*100:.1f}%)")
    
    total_pnl = sum(l.pnl for l in logs)
    avg_win = sum(l.pnl for l in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(l.pnl for l in losing_trades) / len(losing_trades) if losing_trades else 0
    
    print(f"\nTotal P&L: ${total_pnl:.2f}")
    print(f"Average win: ${avg_win:.2f}")
    print(f"Average loss: ${avg_loss:.2f}")
    
    # Exit reasons
    exit_reasons = {}
    for log in logs:
        if log.exit_reason:
            exit_reasons[log.exit_reason] = exit_reasons.get(log.exit_reason, 0) + 1
    
    print(f"\nExit reasons:")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        pnl_for_reason = sum(l.pnl for l in logs if l.exit_reason == reason)
        print(f"  {reason}: {count} trades (${pnl_for_reason:.2f})")
    
    # Strategy breakdown
    strategy_perf = await db.get_performance_by_strategy()
    if strategy_perf:
        print(f"\nStrategy performance:")
        for strategy, stats in strategy_perf.items():
            print(f"  {strategy}:")
            print(f"    Trades: {stats.get('completed_trades', 0)}")
            print(f"    P&L: ${stats.get('total_pnl', 0):.2f}")
            print(f"    Win rate: {stats.get('win_rate_pct', 0):.1f}%")
    
    await db.close()


async def main():
    """Main analysis."""
    # Analyze updated bot
    updated_db = "trading_system.db"
    
    # Check if original bot database exists
    original_db = "../kalshi-bot-original/kalshi-ai-trading-bot/trading_system.db"
    
    if Path(updated_db).exists():
        await analyze_bot(updated_db, "UPDATED BOT")
    else:
        print(f"Updated bot database not found at {updated_db}")
    
    if Path(original_db).exists():
        await analyze_bot(original_db, "ORIGINAL BOT")
    else:
        print(f"\nOriginal bot database not found at {original_db}")
        print("Please provide the correct path to the original bot's database.")


if __name__ == "__main__":
    asyncio.run(main())
