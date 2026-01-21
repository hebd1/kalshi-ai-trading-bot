"""
Quick test to verify dashboard would display strategy correctly
"""
import asyncio
import sys
sys.path.insert(0, '.')

async def test_dashboard_display():
    from src.utils.database import DatabaseManager
    
    db_manager = DatabaseManager()
    await db_manager.initialize()
    
    # Get positions using the fixed method
    positions = await db_manager.get_open_positions()
    
    print(f"✓ Fetched {len(positions)} positions")
    print("\nDashboard display simulation:\n")
    
    for i, pos in enumerate(positions[:5], 1):
        # Simulate what dashboard code does: pos['strategy'] or 'Unknown'
        strategy_display = pos.strategy or 'Unknown'
        
        print(f"{i}. Market: {pos.market_id[:30]}...")
        print(f"   Side: {pos.side}")
        print(f"   Strategy: {strategy_display}")
        print(f"   ✓ Strategy field: {repr(pos.strategy)}")
        print()
    
    # Check for any positions with None strategy
    none_count = sum(1 for pos in positions if pos.strategy is None)
    unknown_count = sum(1 for pos in positions if not pos.strategy)
    
    print(f"Summary:")
    print(f"  Total positions: {len(positions)}")
    print(f"  Positions with strategy=None: {none_count}")
    print(f"  Positions that would show 'Unknown': {unknown_count}")
    
    if unknown_count == 0:
        print(f"\n✅ SUCCESS! All positions have valid strategies.")
        print(f"   Dashboard will display strategy names correctly!")
    else:
        print(f"\n⚠️  WARNING: {unknown_count} positions would still show 'Unknown'")

if __name__ == "__main__":
    asyncio.run(test_dashboard_display())
