from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import config
from datetime import datetime
import uvicorn

# Initialize FastAPI
app = FastAPI(title="Retail Vision API")

# Allow CORS (for Flutter/Web access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Connection Helper
def get_db_connection():
    try:
        conn = psycopg2.connect(config.DB_CONNECTION_STRING)
        return conn
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

@app.get("/")
def read_root():
    return {"message": "Retail Vision API is running"}

@app.get("/api/analytics/live")
def get_live_analytics():
    """
    Returns the current active visitor count.
    Format matches Flutter app expectation:
    {
        "success": true,
        "data": <int_count>
    }
    """
    conn = get_db_connection()
    if not conn:
        return {"success": False, "message": "Database error"}
    
    try:
        cursor = conn.cursor()
        
        # Fetch the latest system status
        query = "SELECT active_visitors, timestamp FROM system_status ORDER BY timestamp DESC LIMIT 1"
        cursor.execute(query)
        row = cursor.fetchone()
        
        active_count = 0
        
        if row:
            count, timestamp = row
            # Calculate staleness
            # If data is older than 15 seconds, assume system is OFFLINE -> 0 visitors
            now = datetime.now()
            # timestamp from DB might be naive or aware depending on setup, generic approach:
            # We'll just trust the count for now, but in a real app check timezone
            # Simpler logic as requested: if it exists, return it, but maybe check if it's super old?
            # Let's check age roughly
            diff = (now - timestamp).total_seconds()
            if diff < 20: # 20 seconds tolerance
                active_count = count
            else:
                active_count = 0 # Stale
                
        cursor.close()
        conn.close()
        
        return {
            "success": True, 
            "data": active_count
        }
        
    except Exception as e:
        if conn: conn.close()
        return {"success": False, "message": str(e)}

from pydantic import BaseModel

class ChatQuery(BaseModel):
    query: str
    language: str = "en"
    session_id: str = "default"

@app.post("/api/chatbot/query")
def chatbot_query(payload: ChatQuery):
    """
    Simple chatbot endpoint to answer questions about visitor counts.
    """
    q_text = payload.query.lower()
    
    # Check intent
    keywords = ["current", "active", "now", "visitor", "people", "many", "count"]
    # Arabic keywords
    keywords_ar = ["كم", "عدد", "الزوار", "الان", "حاليا", "موجود"]
    
    is_asking_count = any(k in q_text for k in keywords) or any(k in q_text for k in keywords_ar)
    
    if is_asking_count:
        # Fetch data
        conn = get_db_connection()
        count = 0
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT active_visitors FROM system_status ORDER BY timestamp DESC LIMIT 1")
                row = cursor.fetchone()
                if row: count = row[0]
                conn.close()
            except:
                pass
        
        # Formulate Response (Matching ChatResponse model)
        if "ar" in payload.language or any(k in q_text for k in keywords_ar):
            response_text = f"يوجد حالياً {count} زوار في المتجر."
        else:
            response_text = f"There are currently {count} visitors in the store."
            
        return {
            "success": True,
            "response": response_text,
            "recommendations": [],
            "context": {"query": payload.query}
        }
    
    else:
        # Fallback
        msg = "I can currently only answer questions about the live visitor count. Try asking 'How many people are there?'"
        if "ar" in payload.language or any(k in q_text for k in keywords_ar):
            msg = "يمكنني حالياً الإجابة فقط على الأسئلة المتعلقة بعدد الزوار المباشر. جرب 'كم عدد الزوار؟'"
            
        return {
            "success": True,
            "response": msg,
            "recommendations": [],
            "context": {"query": payload.query}
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
