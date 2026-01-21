
import sqlite3
import pandas as pd
import os

def inspect_db():
    try:
        db_path = os.path.abspath('production_db.db')
        print(f"Connecting to database at: {db_path}")
        conn = sqlite3.connect(db_path)
        
        # Check positions table
        print("\n--- Positions Table Schema ---")
        cursor = conn.execute("PRAGMA table_info(positions)")
        for row in cursor.fetchall():
            print(row)
            
        print("\n--- Problematic Positions ---")
        # Problematic IDs from logs: 
        # KXMVESPORTSMULTIGAMEEXTENDED-S20257D1F96984AD-8F6FA10756E
        # KXPGATOUR-THAE26-WCLA
        # KXMVESPORTSMULTIGAMEEXTENDED-S202596D5ED67370-93918505B9A
        # KXMVESPORTSMULTIGAMEEXTENDED-S2025C242B40380C-EAA7C1FF1C3
        
        problem_ids = [
            'KXMVESPORTSMULTIGAMEEXTENDED-S20257D1F96984AD-8F6FA10756E', 
            'KXPGATOUR-THAE26-WCLA',
            'KXMVESPORTSMULTIGAMEEXTENDED-S202596D5ED67370-93918505B9A',
            'KXMVESPORTSMULTIGAMEEXTENDED-S2025C242B40380C-EAA7C1FF1C3'
        ]
        
        dfs = []
        for pid in problem_ids:
            query = f"SELECT * FROM positions WHERE market_id = '{pid}'"
            df = pd.read_sql_query(query, conn)
            dfs.append(df)
            
        if dfs:
            combined_csv = pd.concat(dfs)
            if not combined_csv.empty:
                print(combined_csv.to_string())
            else:
                 print("No matching positions found in DB for the problem IDs.")
        else:
            print("No matching positions found in DB.")

        print("\n--- Recent Positions (Last 5) ---")
        df_recent = pd.read_sql_query("SELECT * FROM positions ORDER BY timestamp DESC LIMIT 5", conn)
        print(df_recent.to_string())

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_db()
