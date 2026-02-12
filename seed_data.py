import psycopg2
import random
from datetime import datetime, timedelta
import config

DB_CONNECTION_STRING = config.DB_CONNECTION_STRING

def generate_data():
    print("Starting data generation for January 2026...")
    
    try:
        conn = psycopg2.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()
        
        start_date = datetime(2026, 1, 1)
        end_date = datetime(2026, 1, 31)
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            print(f"Generating data for {date_str}...")
            
            # Shop hours: 9 AM to 9 PM (21:00)
            for hour in range(9, 22):
                # 1. VISITORS (Main Entrance)
                # Random traffic based on hour (Peak at 12-14 and 17-19)
                base_traffic = random.randint(5, 20)
                if 12 <= hour <= 14 or 17 <= hour <= 19:
                    base_traffic += random.randint(10, 30)
                
                cursor.execute(
                    "INSERT INTO visitors (visitor_count, date, hour) VALUES (%s, %s, %s)",
                    (base_traffic, date_str, hour)
                )
                
                # 2. SECTION ANALYTICS
                sections = ["Clothing", "Electronics", "Groceries", "Home"]
                for section in sections:
                    sec_count = int(base_traffic * random.uniform(0.2, 0.5))
                    males = int(sec_count * random.uniform(0.4, 0.6))
                    females = sec_count - males
                    
                    cursor.execute(
                        """INSERT INTO section_analytics 
                           (section_name, visitor_count, male_count, female_count, date, hour) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (section, sec_count, males, females, date_str, hour)
                    )
                
                # 3. CASHIER ANALYTICS
                # 15 minute intervals (4 per hour) -> Aggregate or just 1 log per hour? 
                # Schema allows multiple. Let's insert just one summary per hour for simplicity.
                q_len = random.randint(0, 8)
                is_busy = q_len > 4
                cursor.execute(
                    """INSERT INTO cashier_analytics 
                       (queue_length, is_busy, date, hour) 
                       VALUES (%s, %s, %s, %s)""",
                    (q_len, is_busy, date_str, hour)
                )

                # 4. DWELL TIME (Sample customers)
                # Generate 5-10 random customer records per hour
                for _ in range(random.randint(5, 10)):
                    track_id = random.randint(1000, 99999)
                    sec = random.choice(sections)
                    duration = random.randint(30, 600) # 30s to 10 mins
                    
                    # Entry time: date + hour + random minute
                    entry_dt = current_date + timedelta(hours=hour, minutes=random.randint(0, 50))
                    exit_dt = entry_dt + timedelta(seconds=duration)
                    
                    gender = random.choice(["Man", "Woman"])
                    emotion = random.choice(["Happy", "Neutral", "Neutral", "Surprised"])
                    
                    cursor.execute(
                        """INSERT INTO customer_dwell_time 
                           (track_id, section_name, entry_time, exit_time, duration_seconds, gender, emotion, date, hour) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (track_id, sec, entry_dt, exit_dt, duration, gender, emotion, date_str, hour)
                    )

            current_date += timedelta(days=1)
            conn.commit()

        print("Data generation complete!")
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_data()
