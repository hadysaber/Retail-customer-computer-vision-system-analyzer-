import streamlit as st
import psycopg2
import pandas as pd
import time
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import config

# ==========================================
# CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Retail Vision Analytics (Advanced)",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Use centralized configuration
DB_CONNECTION_STRING = config.DB_CONNECTION_STRING

# Custom CSS for "Premium" Feel
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
        }
        .metric-card {
            background-color: #1E1E1E;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        }
        .metric-value {
            font-size: 2rem;
            font-weight: bold;
            color: #4CAF50;
        }
        .metric-label {
            font-size: 0.9rem;
            color: #AAA;
        }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# DATA LOADING (NEW SCHEMA)
# ==========================================
@st.cache_data(ttl=5)  # Refresh cache every 5 seconds
def load_data():
    try:
        conn = psycopg2.connect(DB_CONNECTION_STRING)
        
        # 1. Daily Summary (Total Visitors)
        query_daily = "SELECT * FROM daily_summary LIMIT 7"
        daily_df = pd.read_sql(query_daily, conn)
        
        # 2. Section Performance
        query_sections = "SELECT * FROM section_performance"
        section_df = pd.read_sql(query_sections, conn)
        
        # 3. Cashier Stats (Real-time)
        query_cashier = "SELECT * FROM cashier_analytics ORDER BY timestamp DESC LIMIT 1"
        cashier_df = pd.read_sql(query_cashier, conn)
        
        # 3. Recent Dwell Times
        query_dwell = "SELECT * FROM customer_dwell_time ORDER BY entry_time DESC LIMIT 50"
        dwell_df = pd.read_sql(query_dwell, conn)
        
        # 4. System Status (Real-time)
        query_status = "SELECT * FROM system_status ORDER BY timestamp DESC LIMIT 1"
        status_df = pd.read_sql(query_status, conn)

        conn.close()
        return daily_df, section_df, cashier_df, dwell_df, status_df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ==========================================
# MAIN DASHBOARD
# ==========================================
def main():
    st.title("📊 Retail Vision Live Analytics")
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()

    daily_df, section_df, cashier_df, dwell_df, status_df = load_data()

    # ==========================================
    # 1. KPI SECTION
    # ==========================================
    c1, c2, c3, c4 = st.columns(4)
    
    # Live Status Logic
    active_now = 0
    cam_status = "OFFLINE"
    if not status_df.empty:
        last_ts = pd.to_datetime(status_df.iloc[0]['timestamp'])
        # Check staleness (if older than 30s, assume offline)
        # Note: server time vs local time might differ slightly, using simple diff
        now = datetime.now()
        diff = (now - last_ts).total_seconds()
        
        if diff < 15: # 15 seconds tolerance
            active_now = status_df.iloc[0]['active_visitors']
            cam_status = status_df.iloc[0]['camera_status']
        else:
            active_now = 0 # Force 0 if stale
            cam_status = "OFFLINE" # Stale data
    
    # Metrics
    today = datetime.now().strftime("%Y-%m-%d")
    
    total_today = 0
    if not daily_df.empty:
        # daily_df has 'date' column
        daily_df['date'] = daily_df['date'].astype(str)
        mask = daily_df['date'] == today
        if mask.any():
            total_today = daily_df.loc[mask, 'total_visitors'].values[0]

    # Cashier Status
    queue_len = 0
    wait_time = "0s"
    status = "OPEN"
    if not cashier_df.empty:
        queue_len = cashier_df.iloc[0]['queue_length']
        status = "BUSY" if cashier_df.iloc[0]['is_busy'] else "IDLE"

    # Avg Dwell
    avg_dwell = 0
    if not dwell_df.empty:
        avg_dwell = dwell_df['duration_seconds'].mean()

    with c1:
        st.metric("Active Visitors (Live)", int(active_now), delta=cam_status, delta_color="normal")
    with c2:
        st.metric("Total Visitors (Today)", int(total_today))
    with c3:
        st.metric("Cashier Queue", f"{queue_len} People", status)
    with c4:
        st.metric("Avg. Dwell Time", f"{avg_dwell:.1f} sec")

    st.markdown("---")

    # ==========================================
    # 2. CHARTS SECTION
    # ==========================================
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Section Popularity")
        if not section_df.empty:
            fig_bar = px.bar(section_df, x='section_name', y='total_visitors', 
                             color='section_name', template="plotly_dark", title="Visitors per Zone")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No section data yet.")

    with col2:
        st.subheader("Demographics by Section")
        if not section_df.empty:
            # Melt for grouped bar chart
            melted = section_df.melt(id_vars=['section_name'], value_vars=['total_male', 'total_female'], 
                                   var_name='Gender', value_name='Count')
            fig_grp = px.bar(melted, x='section_name', y='Count', color='Gender', barmode='group',
                             template="plotly_dark", title="Gender Breakdown per Zone")
            st.plotly_chart(fig_grp, use_container_width=True)
        else:
            st.info("No demographics data yet.")

    # ==========================================
    # 3. RECENT ACTIVITY FEED
    # ==========================================
    st.subheader("📋 Recent Customer Activity (Dwell Time)")
    if not dwell_df.empty:
        st.dataframe(
            dwell_df[['entry_time', 'section_name', 'duration_seconds', 'gender', 'emotion']].head(10),
            use_container_width=True,
            hide_index=True
        )

    # Auto-Refresh
    time.sleep(5)
    st.rerun()

if __name__ == "__main__":
    main()
