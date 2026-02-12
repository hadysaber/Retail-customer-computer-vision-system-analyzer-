import psycopg2
import config

def init_db():
    print("--- Initializing Database ---")
    try:
        # 1. Connect using config.py
        print("Connecting to Supabase...")
        conn = psycopg2.connect(config.DB_CONNECTION_STRING)
        cursor = conn.cursor()
        
        # 2. Read schema.sql
        print("Reading schema.sql...")
        with open('schema.sql', 'r') as f:
            schema_sql = f.read()
            
        # 3. Execute SQL
        print("Executing SQL commands...")
        cursor.execute(schema_sql)
        conn.commit()
        
        print("\n[SUCCESS] Database tables created!")
        conn.close()
        
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize DB: {e}")
        print("Tip: Check your connection string in config.py")

if __name__ == "__main__":
    init_db()
