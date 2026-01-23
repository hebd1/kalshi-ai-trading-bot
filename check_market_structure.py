
import asyncio
import os
import json
from src.clients.kalshi_client import KalshiClient
from src.config.settings import settings

# Configure environment (using demo by default, but checks env vars)
settings.api.configure_environment(use_live=False)

async def check_market_structure():
    client = KalshiClient()
    try:
        print("Fetching markets...")
        # Fetch a small batch of markets
        response = await client.get_markets(limit=20)
        markets = response.get("markets", [])
        
        if not markets:
            print("No markets found.")
            return

        print(f"Found {len(markets)} markets. Inspecting first market:")
        first_market = markets[0]
        print(json.dumps(first_market, indent=2))
        
        # Check for event_ticker or series_ticker
        print("\nChecking for grouping keys:")
        keys_to_check = ['event_ticker', 'series_ticker', 'ticker']
        for key in keys_to_check:
            if key in first_market:
                print(f"✅ Found key: {key} = {first_market[key]}")
            else:
                print(f"❌ Missing key: {key}")

        # Look for mutually exclusive candidates (same event_ticker)
        print("\nGrouping by event_ticker:")
        event_groups = {}
        for m in markets:
            event_ticker = m.get('event_ticker')
            if event_ticker:
                if event_ticker not in event_groups:
                    event_groups[event_ticker] = []
                event_groups[event_ticker].append(m)
        
        for event, group in event_groups.items():
            if len(group) > 1:
                print(f"Event {event} has {len(group)} markets:")
                for m in group:
                    print(f"  - {m.get('ticker')}: {m.get('title')} (Yes Ask: {m.get('yes_ask')}, No Ask: {m.get('no_ask')})")
                
                # Simple arbitrage check
                total_ask_cost = sum(m.get('yes_ask', 9999) for m in group) # yes_ask is in cents
                print(f"  Total YES Ask Cost: {total_ask_cost} cents")
                if total_ask_cost < 100:
                    print("  🚨 POTENTIAL ARBITRAGE DETECTED! 🚨")
                else:
                    print("  No arbitrage (Total >= 100)")
                print("-" * 20)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_market_structure())
