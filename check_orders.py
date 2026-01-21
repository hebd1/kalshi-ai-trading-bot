
import asyncio
from src.clients.kalshi_client import KalshiClient
from src.config.settings import settings

async def check_orders():
    # Force live environment
    settings.api.configure_environment(use_live=True)
    
    client = KalshiClient()
    try:
        print(f"Checking orders for KXAOWOMEN-26-MKEY...")
        response = await client.get_orders(ticker='KXAOWOMEN-26-MKEY')
        
        orders = response.get('orders', [])
        print(f"Found {len(orders)} orders.")
        
        for order in orders:
            print(f"- Order ID: {order.get('order_id')}")
            print(f"  Status: {order.get('status')}")
            print(f"  Action: {order.get('action')}")
            print(f"  Side: {order.get('side')}")
            print(f"  Count: {order.get('count')}")
            print(f"  Remaining: {order.get('remaining_count')}")
            
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_orders())
