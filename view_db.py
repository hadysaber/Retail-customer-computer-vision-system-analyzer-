import psycopg2
import pandas as pd
import config

# Use centralized configuration
DB_CONNECTION_STRING = config.DB_CONNECTION_STRING

print(f"--- Connecting to PostgreSQL ---")
try:
    conn = psycopg2.connect(DB_CONNECTION_STRING)
    cursor = conn.cursor()
    print("Connection successful!")

    # 1. VISITS TABLE
    print("\n[TABLE: VISITS (Top 20)]")
    try:
        df_visits = pd.read_sql_query("SELECT * FROM visits ORDER BY id DESC LIMIT 20", conn)
        if df_visits.empty:
            print("(No visits recorded yet)")
        else:
            print(df_visits.to_string(index=False))
    except Exception as e:
        print(f"Error reading visits: {e}")

    # 2. HEATMAP TABLE
    print("\n[TABLE: HEATMAP POINTS (Count)]")
    try:
        cursor.execute("SELECT COUNT(*) FROM heatmap")
        count = cursor.fetchone()[0]
        print(f"Total Heatmap Points: {count}")
    except Exception as e:
        print(f"Error reading heatmap: {e}")

    # 3. SYSTEM STATUS
    print("\n[TABLE: SYSTEM STATUS (Latest)]")
    try:
        cursor.execute("SELECT * FROM system_status ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            print(f"Timestamp: {row[1]}, Active: {row[2]}, Status: {row[3]}")
        else:
            print("(No status logs yet)")
    except Exception as e:
        print(f"Error reading status: {e}")
    
    conn.close()
    
except Exception as e:
    print(f"Error connecting to DB: {e}")
    print("Tip: Check DB_CONNECTION_STRING in config.py")

input("\nPress Enter to close...")
