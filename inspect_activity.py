
import sqlite3
import pandas as pd
import os

def inspect_activity():
    try:
        db_path = os.path.abspath('production_db.db')
        conn = sqlite3.connect(db_path)
        
        print("\n--- Recent Market Analyses (Last 10) ---")
        try:
            df_analyses = pd.read_sql_query("SELECT * FROM market_analyses ORDER BY analysis_timestamp DESC LIMIT 10", conn)
            print(df_analyses.to_string())
        except Exception as e:
            print(f"Error reading market_analyses: {e}")

        print("\n--- Recent Trade Logs (Last 10) ---")
        try:
            df_trades = pd.read_sql_query("SELECT * FROM trade_logs ORDER BY entry_timestamp DESC LIMIT 10", conn)
            print(df_trades.to_string())
        except Exception as e:
            print(f"Error reading trade_logs: {e}")

        print("\n--- Daily Cost Tracking ---")
        try:
            df_cost = pd.read_sql_query("SELECT * FROM daily_cost_tracking ORDER BY date DESC LIMIT 5", conn)
            print(df_cost.to_string())
        except Exception as e:
            print(f"Error reading daily_cost_tracking: {e}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_activity()
