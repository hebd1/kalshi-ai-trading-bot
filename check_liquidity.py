
import asyncio
from src.clients.kalshi_client import KalshiClient
from src.config.settings import settings

# Configure for production
settings.api.configure_environment(use_live=True)

async def check_orderbook():
    client = KalshiClient()
    ticker = "KXMVESPORTSMULTIGAMEEXTENDED-S20257D1F96984AD-8F6FA10756E"
    
    try:
        print(f"Checking orderbook for {ticker}...")
        orderbook = await client.get_orderbook(ticker)
        print("Orderbook:", orderbook)
        
        market = await client.get_market(ticker)
        print("\nMarket Info:", market.get('market', {}))
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_orderbook())
