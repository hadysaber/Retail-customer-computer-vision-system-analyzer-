-- Retail Analytics System Database Schema
-- Customised for editedOnlyOneID.py (Advanced Version)
-- PostgreSQL Database: supabase

-- Drop existing tables if they exist
DROP TABLE IF EXISTS recommendations CASCADE;
DROP TABLE IF EXISTS traffic_predictions CASCADE;
DROP TABLE IF EXISTS cashier_analytics CASCADE;
DROP TABLE IF EXISTS section_analytics CASCADE;
DROP TABLE IF EXISTS visitors CASCADE;
DROP TABLE IF EXISTS visits CASCADE; -- Drop old table just in case
DROP TABLE IF EXISTS heatmap CASCADE; -- Drop old table just in case

-- 1. Visitors table (Main entrance counts)
CREATE TABLE visitors (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    visitor_count INTEGER NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Section Analytics table (Zone tracking)
CREATE TABLE section_analytics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    section_name VARCHAR(100) NOT NULL,
    visitor_count INTEGER NOT NULL,
    male_count INTEGER DEFAULT 0,
    female_count INTEGER DEFAULT 0,
    object_counts JSONB, -- Stores {"cell phone": 2, "chair": 5}
    heatmap_data JSONB, -- Can store encoded points if needed
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Customer Dwell Time table (Detailed per-person tracking)
CREATE TABLE customer_dwell_time (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL,
    section_name VARCHAR(100) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    duration_seconds FLOAT,
    gender VARCHAR(50), -- Added to support demographics
    emotion VARCHAR(50), -- Added to support demographics
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Cashier Analytics table (Queue analysis)
CREATE TABLE cashier_analytics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    queue_length INTEGER NOT NULL,
    estimated_wait_time FLOAT,
    is_busy BOOLEAN DEFAULT FALSE,
    estimated_transactions INTEGER DEFAULT 0,
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Traffic Predictions table (AI forecasting)
CREATE TABLE traffic_predictions (
    id SERIAL PRIMARY KEY,
    prediction_date DATE NOT NULL,
    prediction_hour INTEGER NOT NULL,
    predicted_visitors INTEGER NOT NULL,
    confidence_level FLOAT,
    model_used VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(prediction_date, prediction_hour)
);

-- 6. Recommendations table (AI insights)
CREATE TABLE recommendations (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recommendation_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'medium',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_visitors_date_hour ON visitors(date, hour);
CREATE INDEX idx_section_date_hour ON section_analytics(date, hour);
CREATE INDEX idx_dwell_date_hour ON customer_dwell_time(date, hour);
CREATE INDEX idx_cashier_date_hour ON cashier_analytics(date, hour);
CREATE INDEX idx_predictions_date_hour ON traffic_predictions(prediction_date, prediction_hour);

-- VIEWS for Dashboard
CREATE OR REPLACE VIEW daily_summary AS
SELECT 
    date,
    SUM(visitor_count) as total_visitors,
    AVG(visitor_count) as avg_hourly_visitors,
    MAX(visitor_count) as peak_visitors
FROM visitors
GROUP BY date
ORDER BY date DESC;

CREATE OR REPLACE VIEW section_performance AS
SELECT 
    section_name,
    date,
    SUM(visitor_count) as total_visitors,
    SUM(male_count) as total_male,
    SUM(female_count) as total_female
FROM section_analytics
GROUP BY section_name, date
ORDER BY date DESC, total_visitors DESC;

-- 7. System Status table (Real-time active counts)
CREATE TABLE IF NOT EXISTS system_status (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_visitors INTEGER DEFAULT 0,
    camera_status VARCHAR(50) DEFAULT 'OK', -- 'OK', 'NO SIGNAL', 'OFFLINE'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast retrieval of latest status
CREATE INDEX idx_system_status_timestamp ON system_status(timestamp DESC);

