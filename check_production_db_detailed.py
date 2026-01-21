
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

db_path = "production_db.db"

def analyze_db():
    conn = sqlite3.connect(db_path)
    
    print("=== Database Analysis ===")
    
    # 1. Check recent positions (ALL positions, not just open)
    print("\n--- Recent Positions (Last 10) ---")
    try:
        query = """
        SELECT id, market_id, side, entry_price, quantity, status, timestamp, strategy, tracked
        FROM positions 
        ORDER BY timestamp DESC LIMIT 10
        """
        df = pd.read_sql_query(query, conn)
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Error querying positions: {e}")

    # 2. Check Orders table (Crucial to see if orders were placed but not tracked as 'TradeLog')
    print("\n--- Recent Orders (Last 10) ---")
    try:
        query = """
        SELECT id, market_id, side, action, status, quantity, price, created_at, kalshi_order_id 
        FROM orders 
        ORDER BY created_at DESC LIMIT 10
        """
        df = pd.read_sql_query(query, conn)
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Error querying orders: {e}")

    # 3. Check recent closed trades (TradeLog)
    print("\n--- Recent Trade Logs (Last 5) ---")
    try:
        query = """
        SELECT market_id, side, entry_price, exit_price, pnl, exit_reason, exit_timestamp 
        FROM trade_logs 
        ORDER BY exit_timestamp DESC LIMIT 5
        """
        df = pd.read_sql_query(query, conn)
        if df.empty:
            print("No trade logs found.")
        else:
            print(df.to_string(index=False))
    except Exception as e:
        print(f"Error querying trade_logs: {e}")

    # 4. Check LLM Queries
    print("\n--- LLM Query Stats ---")
    try:
        query = """
        SELECT count(*) as total_queries, max(timestamp) as last_query 
        FROM llm_queries
        """
        df = pd.read_sql_query(query, conn)
        print(df.to_string(index=False))
        
        # Show last query details
        query_detail = """
        SELECT timestamp, strategy, market_id, cost_usd 
        FROM llm_queries ORDER BY timestamp DESC LIMIT 3
        """
        df_detail = pd.read_sql_query(query_detail, conn)
        if not df_detail.empty:
            print("\nLast 3 LLM Queries:")
            print(df_detail.to_string(index=False))
            
    except Exception as e:
        print(f"Error querying llm_queries: {e}")
        
    # 5. Check Market Analysis (Cost Tracking)
    print("\n--- Market Analyses (Cost Tracking) ---")
    try:
        query = """
        SELECT count(*) as count, sum(cost_usd) as total_cost, max(analysis_timestamp) as last_analysis
        FROM market_analyses
        """
        df = pd.read_sql_query(query, conn)
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Error querying market_analyses: {e}")

    conn.close()

if __name__ == "__main__":
    analyze_db()
