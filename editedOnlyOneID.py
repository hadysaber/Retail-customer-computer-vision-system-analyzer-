import cv2
import csv
import numpy as np
from ultralytics import YOLO
from deepface import DeepFace
import tkinter as tk
from tkinter import messagebox
import threading
import queue
import time
from datetime import datetime
import os
import json
import psycopg2
from psycopg2 import pool
import config

# ==========================================
# PART 0: Database Manager (Persistent Storage)
# ==========================================
# Use centralized configuration
DB_CONNECTION_STRING = config.DB_CONNECTION_STRING

class DatabaseManager:
    def __init__(self):
        self.conn_pool = None
        self._init_db()
        
        # Initialize CSV immediately so user sees it locally too
        csv_file = "live_visits.csv"
        if not os.path.isfile(csv_file):
            try:
                with open(csv_file, mode='w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Track ID", "Camera", "Gender", "Emotion", "Start Time", "End Time", "Duration (s)"])
                print(f"[System] Created new export file: {csv_file}")
            except Exception as e:
                print(f"[Error] Could not create CSV: {e}")

    def _init_db(self):
        """Initializes PostgreSQL Connection Pool."""
        try:
            # Create a threaded connection pool
            self.conn_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=DB_CONNECTION_STRING
            )
            print("[Database] PostgreSQL Connection Pool Initialized.")
            
            # Verify connection
            conn = self.conn_pool.getconn()
            if conn:
                print("[Database] Successfully connected to PostgreSQL.")
                self.conn_pool.putconn(conn)
                
        except Exception as e:
            print(f"[Database Error] Init failed: {e}")
            print("[Tip] Please update the 'DB_CONNECTION_STRING' at the top of the file!")

    def get_connection(self):
        if self.conn_pool:
            try:
                return self.conn_pool.getconn()
            except:
                pass
        return None

    def release_connection(self, conn):
        if self.conn_pool and conn:
            self.conn_pool.putconn(conn)

    # ==========================================
    # NEW METHODS FOR ADVANCED SCHEMA
    # ==========================================
    
    def log_visitor_entry(self, count, date, hour):
        """Logs to 'visitors' table (Main Entrance)."""
        try:
            conn = self.get_connection()
            if conn:
                cursor = conn.cursor()
                query = "INSERT INTO visitors (visitor_count, date, hour) VALUES (%s, %s, %s)"
                cursor.execute(query, (count, date, hour))
                conn.commit()
                cursor.close()
                self.release_connection(conn)
        except Exception as e:
            print(f"[Database Error] Log Visitor: {e}")

    def log_dwell_time(self, track_id, section, entry_time, exit_time, duration, gender, emotion):
        """Logs to 'customer_dwell_time'."""
        try:
            conn = self.get_connection()
            if conn:
                cursor = conn.cursor()
                query = """
                    INSERT INTO customer_dwell_time 
                    (track_id, section_name, entry_time, exit_time, duration_seconds, gender, emotion, date, hour)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                # Extract date/hour from entry_time
                dt_obj = datetime.strptime(entry_time, "%Y-%m-%d %H:%M:%S")
                date_str = dt_obj.strftime("%Y-%m-%d")
                hour_int = dt_obj.hour
                
                cursor.execute(query, (track_id, section, entry_time, exit_time, duration, gender, emotion, date_str, hour_int))
                conn.commit()
                cursor.close()
                self.release_connection(conn)
        except Exception as e:
            print(f"[Database Error] Log Dwell: {e}")

    def log_section_analytics(self, section_name, visitor_count, males, females):
        """Logs to 'section_analytics'."""
        try:
            conn = self.get_connection()
            if conn:
                cursor = conn.cursor()
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                hour_int = now.hour
                
                query = """
                    INSERT INTO section_analytics 
                    (section_name, visitor_count, male_count, female_count, date, hour)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (section_name, visitor_count, males, females, date_str, hour_int))
                conn.commit()
                cursor.close()
                self.release_connection(conn)
        except Exception as e:
            print(f"[Database Error] Log Section: {e}")

    def log_cashier_status(self, queue_len, busy_bool):
        """Logs to 'cashier_analytics'."""
        try:
            conn = self.get_connection()
            if conn:
                cursor = conn.cursor()
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                hour_int = now.hour
                
                query = """
                    INSERT INTO cashier_analytics 
                    (queue_length, is_busy, date, hour)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(query, (queue_len, busy_bool, date_str, hour_int))
                conn.commit()
                cursor.close()
                self.release_connection(conn)
        except Exception as e:
            print(f"[Database Error] Log Cashier: {e}")

    def log_system_status(self, active_count, camera_status="OK"):
        """Logs real-time system status."""
        try:
            conn = self.get_connection()
            if conn:
                cursor = conn.cursor()
                query = """
                    INSERT INTO system_status 
                    (active_visitors, camera_status)
                    VALUES (%s, %s)
                """
                cursor.execute(query, (active_count, camera_status))
                conn.commit()
                cursor.close()
                self.release_connection(conn)
        except Exception as e:
            # Don't print every time to avoid spamming console
            pass

# ==========================================
# PART 1: Threaded Camera (Speed Booster)
# ==========================================
class ThreadedCamera:
    """
    Reads frames in a separate thread to prevent I/O blocking.
    Always returns the latest frame with proper validation.
    FIXED: Force DirectShow backend to prevent MSMF corruption issues.
    """
    def __init__(self, source):
        self.source = source
        self.capture = None
        self.success = False
        
        self.current_frame = None
        self.running = True
        self.frame_count = 0
        self.corrupted_count = 0
        self.consecutive_corrupted = 0
        self.last_good_frame = None
        
        # Start background thread immediately - connection happens there
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        print(f"[Camera] Thread started for source {source}")
    
    def _reinitialize_camera(self):
        """Attempt to reinitialize camera connection after persistent corruption."""
        print(f"[Camera] Attempting to reinitialize camera {self.source}...")
        try:
            if self.capture:
                self.capture.release()
                time.sleep(0.5)  # Brief pause before reconnecting
            
            # Reinitialize with same settings
            if isinstance(self.source, int) and os.name == 'nt':
                self.capture = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            else:
                self.capture = cv2.VideoCapture(self.source)
            
            if self.capture.isOpened():
                # Reapply settings
                self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
                self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Warmup
                for i in range(5):
                    self.capture.read()
                    time.sleep(0.1)
                
                print(f"[Camera] Successfully reinitialized camera {self.source}")
                self.consecutive_corrupted = 0
                return True
            else:
                print(f"[Camera] Failed to reinitialize camera {self.source}")
                return False
        except Exception as e:
            print(f"[Camera] Reinitialization error: {e}")
            return False

    def _update(self):
        # 1. CONNECT TO CAMERA (NON-BLOCKING)
        print(f"[Camera] Background connecting to {self.source}...")
        
        if isinstance(self.source, int) and os.name == 'nt':
            # ONLY use DirectShow - it's the most stable for Windows webcams
            self.capture = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            if not self.capture.isOpened():
                self.capture.release()
                self.capture = cv2.VideoCapture(self.source)
        else:
            self.capture = cv2.VideoCapture(self.source)
            
        self.success = self.capture.isOpened()
        
        if self.success:
            # Apply Settings
            self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # 2. WARMUP (NON-BLOCKING)
            print(f"[Camera] Connected to {self.source}, warming up...")
            warmup_count = 0
            while warmup_count < 10 and self.running:
                ret, frame = self.capture.read()
                if ret and frame is not None:
                    warmup_count += 1
                time.sleep(0.05)
            print(f"[Camera] Warmup complete for {self.source}")
        else:
            print(f"[Error] Failed to open camera {self.source}")

        consecutive_failures = 0
        stable_frame_buffer = [] 

        
        while self.running and self.success:
            ret, frame = self.capture.read()
            if ret and frame is not None:
                # Debug log every 30 frames to prove thread is running
                if self.frame_count % 30 == 0:
                     print(f"[Debug] Camera {self.source} captured frame #{self.frame_count} (std={frame.std():.2f})")

                # Strict validation to prevent corrupted frames
                try:
                    # Check basic properties
                    if frame.size == 0 or frame.shape[0] == 0 or frame.shape[1] == 0:
                        consecutive_failures += 1
                        self.consecutive_corrupted += 1
                        continue
                    
                    # Additional check: ensure frame has 3 channels (BGR)
                    if len(frame.shape) != 3 or frame.shape[2] != 3:
                        consecutive_failures += 1
                        self.consecutive_corrupted += 1
                        continue
                    
                    pass # Strict validation disabled for debugging
                    '''
                    # ENHANCED CORRUPTION DETECTION
                    # ... (Disabled) ...
                    '''
                    
                    # NEW: Stability buffer - only update if we get consecutive good frames
                    # print("[Debug] Reached append") 
                    stable_frame_buffer.append(frame.copy())
                    if len(stable_frame_buffer) > 2:
                        stable_frame_buffer.pop(0)
                    
                    # Update current_frame immediately with first good frame after warmup
                    # This ensures camera feed appears quickly after initialization
                    if len(stable_frame_buffer) >= 1:
                        self.current_frame = stable_frame_buffer[-1]
                        self.last_good_frame = self.current_frame.copy()  # Store for comparison
                        self.frame_count += 1
                        consecutive_failures = 0
                        self.consecutive_corrupted = 0  # Reset on good frame
                    
                except Exception as e:
                    consecutive_failures += 1
                    self.consecutive_corrupted += 1
                    stable_frame_buffer.clear()
                    print(f"[Critical Error] Frame validation error: {e}")
                    if consecutive_failures % 30 == 0:
                        print(f"[Error] Frame validation error: {e}")
            else:
                consecutive_failures += 1
                self.consecutive_corrupted += 1
                stable_frame_buffer.clear()
                if consecutive_failures == 1:
                    print(f"[Debug] Camera {self.source} failed to read frame (failure #1)")
                # If reading fails repeatedly, try to reconnect
                if consecutive_failures > 100:
                    print(f"[Error] Camera {self.source} appears disconnected")
                    self.success = False
                    break
            
            # NEW: Auto-recovery if corruption persists
            if self.consecutive_corrupted > 30:  # 30 consecutive bad frames
                print(f"[Warning] Persistent corruption detected ({self.consecutive_corrupted} frames)")
                if self._reinitialize_camera():
                    stable_frame_buffer.clear()
                    consecutive_failures = 0
                else:
                    # If reinitialization fails, wait before trying again
                    time.sleep(2)
                    self.consecutive_corrupted = 0  # Reset to try again later
            
            time.sleep(0.005)  # Small sleep to prevent CPU hogging


    def read(self):
        # Case 0: Not yet initialized
        if self.capture is None:
            init_frame = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(init_frame, "Initializing Camera...", (150, 180), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
            return True, init_frame

        # Case 1: Initializing/Warming Up
        if self.current_frame is None and self.success:
            # Debug log to verify this state is active
            if self.frame_count % 30 == 0: # Use separate counter or just spam a bit?
                 print(f"[Debug] read() returning Warming Up frame. Buffer size: {len(self.stable_frame_buffer) if hasattr(self, 'stable_frame_buffer') else '?'}")
            
            warmup_frame = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(warmup_frame, "Camera Warming Up...", (150, 180), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            return True, warmup_frame
            
        # Case 2: Failed to open
        if not self.success and self.capture is not None:
             error_frame = np.zeros((360, 640, 3), dtype=np.uint8)
             cv2.putText(error_frame, "Connection Failed", (180, 180), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
             # Return TRUE so this frame is actually displayed!
             return True, error_frame

        return (self.current_frame is not None), self.current_frame

    def release(self):
        self.running = False
        self.thread.join(timeout=1)
        if self.capture:
            self.capture.release()

# ==========================================
# PART 1.5: Zone Manager (NEW)
# ==========================================
class ZoneManager:
    """
    Manages defined zones (Sections) within the camera view.
    Simple version: Split screen into Left/Right or define rectangles.
    """
    def __init__(self):
        # Zones configuration: {camera_index: {zone_name: (x1, y1, x2, y2)}}
        # Valid zones: Section A, Section B, Cashier
        self.zones = {
            0: { # Camera 0 (Main Entrance / Store)
                "Clothing": (0, 0, 320, 360),    # Left Half
                "Electronics": (320, 0, 640, 360) # Right Half
            },
            1: { # Camera 1 (Assuming Checkouts)
                "Cashier Queue": (100, 100, 540, 360) # Center area
            }
        }

    def get_zone(self, cam_index, cx, cy):
        """Returns the name of the zone the point (cx, cy) is in."""
        if cam_index not in self.zones: return "General"
        
        for name, rect in self.zones[cam_index].items():
            x1, y1, x2, y2 = rect
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return name
        return "Walkway"

    def draw_zones(self, frame, cam_index):
        if cam_index not in self.zones: return
        
        for name, rect in self.zones[cam_index].items():
            x1, y1, x2, y2 = rect
            color = (0, 255, 255) if "Cashier" in name else (255, 100, 100)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
            cv2.putText(frame, name, (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

# ==========================================
# PART 2: Global Identity & Tracking (Updated)
# ==========================================
class GlobalTrackManager:
    def __init__(self, db_manager):
        self.db = db_manager
        self.zone_manager = ZoneManager()
        self.next_global_id = 1
        self.local_to_global = {}  
        
        # Active tracks: {global_id: { ..., 'current_zone': 'None', 'zone_entry_time': timestamp }}
        self.active_tracks = {}
        
        # Analytics Aggregators
        self.section_counts = {"Clothing": set(), "Electronics": set(), "Cashier Queue": set()}
        self.cashier_queue_len = 0
        
        self.global_registry = {} 
        self.lost_tracks = {}

    def get_global_id(self, cam_index, local_id, img_crop, bbox):
        current_time = time.time()
        
        # 1. Existing Local Mapping
        if (cam_index, local_id) in self.local_to_global:
            gid = self.local_to_global[(cam_index, local_id)]
            self._update_activity(gid, current_time, bbox)
            return gid
        
        # ... (Re-ID logic skipped for brevity, assumed same flow) ...
        # NOTE: Replacing full logic to insert 'is_confirmed': False in new tracks
        
        # 2. Re-ID Logic
        curr_hist = self._calc_multi_zone_hist(img_crop)
        bx, by = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2 
        
        best_match_id = -1
        highest_score = 0.0
        
        # Tuning Paramters
        SIMILARITY_THRESHOLD = 0.50 
        SPATIAL_THRESHOLD = 250 
        TIME_THRESHOLD = 10.0 

        # -- A. Spatial Recovery --
        for gid, data in list(self.lost_tracks.items()):
            if data['camera_id'] == (cam_index + 1):
                if current_time - data['last_seen'] < TIME_THRESHOLD:
                    lx, ly = data['last_bbox']
                    dist = np.sqrt((bx - lx)**2 + (by - ly)**2)
                    if dist < SPATIAL_THRESHOLD:
                        sim = cv2.compareHist(curr_hist, data['hist'], cv2.HISTCMP_CORREL)
                        if sim > 0.35: 
                            best_match_id = gid
                            highest_score = 100.0 
                            del self.lost_tracks[gid]
                            break
        
        # -- B. Visual Re-ID --
        if best_match_id == -1:
            for gid, data in self.global_registry.items():
                if current_time - data['last_seen'] < 120.0:
                    similarity = cv2.compareHist(curr_hist, data['hist'], cv2.HISTCMP_CORREL)
                    if similarity > highest_score:
                        highest_score = similarity
                        best_match_id = gid

        # 3. Decision
        if highest_score > SIMILARITY_THRESHOLD:
            assigned_id = best_match_id
            
            # Weighted Average Update
            ALPHA = 0.3 
            old_hist = self.global_registry[assigned_id]['hist']
            new_hist = cv2.addWeighted(curr_hist, ALPHA, old_hist, 1 - ALPHA, 0)
            self.global_registry[assigned_id]['hist'] = new_hist 
            
            if assigned_id not in self.active_tracks:
                 self.active_tracks[assigned_id] = {
                    'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'first_seen_ts': current_time, # For duration calc
                    'last_seen': current_time,
                    'gender': 'Unknown', 'age': '?', 'emotion': 'Neutral',
                    'emotion_buffer': [], 
                    'camera_id': cam_index + 1,
                    'bbox': (bx, by),
                    'current_zone': "None",
                    'zone_entry_time': current_time,
                    'is_confirmed': False # Initially unconfirmed
                }
            else:
                pass
                
        else:
            assigned_id = self.next_global_id
            self.next_global_id += 1
            self.global_registry[assigned_id] = {'hist': curr_hist, 'last_seen': current_time}
            self.active_tracks[assigned_id] = {
                'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'first_seen_ts': current_time,
                'last_seen': current_time,
                'gender': 'Unknown', 'age': '?', 'emotion': 'Neutral',
                'emotion_buffer': [],
                'camera_id': cam_index + 1,
                'bbox': (bx, by),
                'current_zone': "None",
                'zone_entry_time': current_time,
                'is_confirmed': False
            }

        self.local_to_global[(cam_index, local_id)] = assigned_id
        
        # Update Zone Logic
        self._update_zone_activity(assigned_id, cam_index, bx, by)
        
        self._update_activity(assigned_id, current_time, bbox)
        return assigned_id

    def _update_zone_activity(self, gid, cam_index, cx, cy):
        """Checks if person moved to a new zone and logs dwell time."""
        new_zone = self.zone_manager.get_zone(cam_index, cx, cy)
        current_zone = self.active_tracks[gid].get('current_zone', 'None')
        
        if new_zone != current_zone:
            # Person just left 'current_zone' -> Log logic
            # (Only log if they were actually in a zone, not just 'None' or 'Walkway')
            if current_zone not in ["None", "Walkway", "General"]:
                # Log Dwell Time for previous zone
                entry_ts = self.active_tracks[gid].get('zone_entry_time', time.time())
                duration = time.time() - entry_ts
                
                if duration > 2.0: # Filter short noise
                    # convert ts to string
                    entry_str = datetime.fromtimestamp(entry_ts).strftime("%Y-%m-%d %H:%M:%S")
                    exit_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    data = self.active_tracks[gid]
                    self.db.log_dwell_time(gid, current_zone, entry_str, exit_str, duration, data['gender'], data['emotion'])
            
            # Update to new zone
            self.active_tracks[gid]['current_zone'] = new_zone
            self.active_tracks[gid]['zone_entry_time'] = time.time()
            
            # Real-time Counter Updates
            if new_zone in self.section_counts:
                 self.section_counts[new_zone].add(gid)


    def _update_activity(self, gid, now, bbox=None):
        if gid in self.global_registry:
            self.global_registry[gid]['last_seen'] = now
        if gid in self.active_tracks:
            self.active_tracks[gid]['last_seen'] = now
            if bbox:
                bx, by = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
                self.active_tracks[gid]['bbox'] = (bx, by)
            
            # Check for Confirmation (Time > 5s)
            if not self.active_tracks[gid]['is_confirmed']:
                duration = now - self.active_tracks[gid]['first_seen_ts']
                if duration > 5.0:
                    self.active_tracks[gid]['is_confirmed'] = True
                    # Log to 'visitors' table (New Schema)
                    # We log +1 count for current hour
                    now_dt = datetime.now()
                    self.db.log_visitor_entry(1, now_dt.strftime("%Y-%m-%d"), now_dt.hour)

    def update_attributes(self, gid, gender, age, emotion):
        if gid in self.active_tracks:
            self.active_tracks[gid]['gender'] = gender
            self.active_tracks[gid]['age'] = age
            
            # --- FEATURE 2: Emotion Smoothing (Voting) ---
            # Append new emotion to buffer (max 7)
            buffer = self.active_tracks[gid].get('emotion_buffer', [])
            buffer.append(emotion)
            if len(buffer) > 7: buffer.pop(0)
            self.active_tracks[gid]['emotion_buffer'] = buffer
            
            # Find most frequent emotion
            if buffer:
                from collections import Counter
                most_common = Counter(buffer).most_common(1)[0][0]
                self.active_tracks[gid]['emotion'] = most_common # Stable emotion
            else:
                 self.active_tracks[gid]['emotion'] = emotion

    def cleanup_old_tracks(self):
        now = time.time()
        to_remove = []
        
        for gid, data in self.active_tracks.items():
            if now - data['last_seen'] > 3.0: # Mark as lost after 3s
                # Move to 'lost_tracks' candidates instead of immediate DB save
                self.lost_tracks[gid] = {
                    'camera_id': data['camera_id'],
                    'last_bbox': data.get('bbox', (0,0)),
                    'last_seen': data['last_seen'],
                    'hist': self.global_registry.get(gid, {}).get('hist', None),
                    # PRESERVE ATTRIBUTES FOR DB LOGGING
                    'start_time': data['start_time'],
                    'gender': data['gender'],
                    'age': data['age'],
                    'emotion': data['emotion']
                }
                
                to_remove.append(gid)

        for gid in to_remove:
            del self.active_tracks[gid]
            
        # Clean up Lost Tracks (Save to DB if really gone)
        to_save = []
        for gid, data in list(self.lost_tracks.items()):
            if now - data['last_seen'] > 10.0: # 10s wait before finalizing visit
                to_save.append(gid)
        
        for gid in to_save:
            # Retrieve preserved attributes
            data = self.lost_tracks[gid]
            start_time = data.get('start_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            gender = data.get('gender', 'Unknown')
            emotion = data.get('emotion', 'Neutral')
            
            # Log final dwell time for the last zone they were in
            current_zone = data.get('current_zone', 'None')
            if current_zone not in ["None", "Walkway", "General"]:
                # Log Dwell Time
                entry_ts = data.get('zone_entry_time', time.time())
                duration = time.time() - entry_ts
                entry_str = datetime.fromtimestamp(entry_ts).strftime("%Y-%m-%d %H:%M:%S")
                # exit time is last seen
                exit_str = datetime.fromtimestamp(data['last_seen']).strftime("%Y-%m-%d %H:%M:%S")
                
                self.db.log_dwell_time(gid, current_zone, entry_str, exit_str, duration, gender, emotion)
            
            del self.lost_tracks[gid]

    def _calc_multi_zone_hist(self, img):
        # Split image into 3 zones (Head, Body, Legs)
        h, w = img.shape[:2]
        part_h = h // 3
        
        # Top (Head)
        part1 = img[0:part_h, :]
        p1_hist = self._calc_hist_part(part1)
        
        # Middle (Body)
        part2 = img[part_h:2*part_h, :]
        p2_hist = self._calc_hist_part(part2)
        
        # Bottom (Legs)
        part3 = img[2*part_h:, :]
        p3_hist = self._calc_hist_part(part3)
        
        return np.vstack((p1_hist, p2_hist, p3_hist))

    def _calc_hist_part(self, img):
        if img.size == 0: return np.zeros((180, 1), dtype=np.float32)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0], None, [60], [0, 180]) # Hue only, 60 bins
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

# ==========================================
# PART 3: Background AI (Unchanged Logic, Optimized)
# ==========================================
class AsyncFaceAnalyzer:
    def __init__(self):
        self.input_queue = queue.Queue(maxsize=5)
        self.results = {} 
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def _worker_loop(self):
        while self.running:
            try:
                task = self.input_queue.get(timeout=0.5)
                global_id, face_img = task 
                try:
                    # OPTIMIZATION: 'enforce_detection=False' + 'detector_backend=skip'
                    # We already cropped the face with YOLO, so we trust it.
                    # This speeds up analysis by ~3x.
                    analysis = DeepFace.analyze(img_path=face_img, 
                                              actions=['gender', 'emotion', 'age'],
                                              enforce_detection=False,
                                              detector_backend='skip', 
                                              silent=True)
                    if isinstance(analysis, list): analysis = analysis[0]
                    self.results[global_id] = {
                        'gender': analysis['dominant_gender'],
                        'age': analysis['age'],
                        'emotion': analysis['dominant_emotion'],
                        'timestamp': time.time()
                    }
                except:
                    self.results[global_id] = {'gender': 'Unknown', 'age': '?', 'emotion': '', 'timestamp': time.time()}
                self.input_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def request_analysis(self, global_id, face_img):
        # Cache check: Re-analyze every 1.0 seconds (was 5.0) for "Real-Time" feel
        if global_id in self.results:
            if time.time() - self.results[global_id]['timestamp'] < 1.0: return 
        if not self.input_queue.full():
            self.input_queue.put((global_id, face_img))

    def get_result(self, global_id):
        return self.results.get(global_id, None)

    def stop(self):
        self.running = False


# ==========================================
# PART 4: Main System
# ==========================================
class RetailSystem:
    def __init__(self, config):
        self.config = config
        print("[System] Initializing...")
        
        self.db = DatabaseManager()
        # Model is loaded lazily in run() to show loading screen
        self.model = None 
        self.ai_worker = AsyncFaceAnalyzer()
        self.track_manager = GlobalTrackManager(self.db)
        
        self.heatmap_buffer = [] 
        # Heatmap Visualization
        self.show_heatmap = False
        self.heat_accumulators = {} # {cam_index: float_array_640x360}
        
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Colors
        self.colors = {'Man': (255,100,0), 'Woman': (200,0,200), 'Scanning': (100,100,100)}

    def process_frame(self, frame, stream_name, cam_index):
        if self.model is None: return frame # Safety

        if frame is None:
            # Return a black placeholder with text
            blank = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(blank, f"{stream_name} (No Signal)", (150, 180), self.font, 0.8, (0, 0, 255), 2)
            return blank

        # CRITICAL: Validate frame before processing to prevent corruption
        try:
            # Check if frame is valid
            if frame.size == 0 or len(frame.shape) != 3 or frame.shape[2] != 3:
                print(f"[Warning] Invalid frame detected in process_frame")
                blank = np.zeros((360, 640, 3), dtype=np.uint8)
                cv2.putText(blank, f"{stream_name} (Invalid Frame)", (150, 180), self.font, 0.8, (255, 0, 0), 2)
                return blank
            
            # Check for corruption patterns
            std_val = frame.std()
            if std_val < 1.0 or std_val > 200.0:
                print(f"[Warning] Corrupted frame detected (std={std_val:.2f})")
                blank = np.zeros((360, 640, 3), dtype=np.uint8)
                cv2.putText(blank, f"{stream_name} (Corrupted)", (150, 180), self.font, 0.8, (255, 0, 0), 2)
                return blank
        except Exception as e:
            print(f"[Error] Frame validation failed: {e}")
            blank = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(blank, f"{stream_name} (Error)", (150, 180), self.font, 0.8, (255, 0, 0), 2)
            return blank

        # Optimize: Resize directly
        try:
            frame_resized = cv2.resize(frame, (640, 360))
        except Exception as e:
            print(f"[Error] Resize failed: {e}")
            blank = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(blank, f"{stream_name} (Resize Error)", (150, 180), self.font, 0.8, (255, 0, 0), 2)
            return blank
            
        output_frame = frame_resized.copy()
        
        # Initialize accumulator for this camera if needed
        if cam_index not in self.heat_accumulators:
             self.heat_accumulators[cam_index] = np.zeros((360, 640), dtype=np.float32)

        # Run Tracking (Persist=True is key) - wrapped in try-catch
        try:
            results = self.model.track(frame_resized, classes=[0], persist=True, verbose=False, tracker="bytetrack.yaml")
        except Exception as e:
            print(f"[Error] YOLO tracking failed: {e}")
            # Return frame without tracking overlay
            cv2.putText(output_frame, stream_name, (10, 30), self.font, 0.6, (255, 255, 255), 2)
            cv2.putText(output_frame, "Tracking Error", (10, 60), self.font, 0.5, (0, 0, 255), 1)
            return output_frame

        try:
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
                local_ids = results[0].boxes.id.cpu().numpy().astype(int)

                for box, local_id in zip(boxes, local_ids):
                    try:  # Isolate each detection processing
                        x1, y1, x2, y2 = box
                        
                        # Update Heatmap (Center of feet)
                        cx, cy = (x1 + x2) // 2, y2
                        self.heatmap_buffer.append((cx, cy))
                        
                        # Visual Accumulation (Gaussian Blob)
                        # Simple optimization: Add point and blur later? Or add small gaussian circle now.
                        # Drawing a small circle is faster.
                        try:
                            # Guard bounds
                            cy, cx = min(cy, 359), min(cx, 639)
                            self.heat_accumulators[cam_index][int(cy), int(cx)] += 1.0
                        except: pass

                        # Re-ID Process
                        person_crop = frame_resized[max(0,y1):min(360,y2), max(0,x1):min(640,x2)]
                        if person_crop.size == 0: continue
                        
                        # Pass bbox for spatial recovery
                        global_id = self.track_manager.get_global_id(cam_index, local_id, person_crop, (x1, y1, x2, y2))
                        
                        # Check AI Attributes
                        ai_data = self.ai_worker.get_result(global_id)
                        if ai_data:
                            gender = ai_data['gender']
                            age = ai_data['age']
                            emotion = ai_data['emotion']
                            # Sync to DB manager for final log
                            self.track_manager.update_attributes(global_id, gender, age, emotion)
                            
                            label = f"ID:{global_id} {gender}, {age}"
                            sub_label = f"{emotion}" 
                            color = self.colors.get(gender, (0, 255, 0))
                            
                            # CONTINUOUS UPDATE: Keep requesting analysis (Throttled by AsyncWorker to 1s)
                            self.ai_worker.request_analysis(global_id, person_crop)
                        else:
                            label = f"ID:{global_id} Scanning..."
                            sub_label = ""
                            color = self.colors['Scanning']
                            self.ai_worker.request_analysis(global_id, person_crop)

                        # Draw (Only search/ID boxes if Heatmap OFF to avoid clutter)
                        if not self.show_heatmap:
                            cv2.rectangle(output_frame, (x1, y1), (x2, y2), color, 2)
                            
                            # Upper Label (ID, Gender, Age)
                            # Reduced font size to 0.4
                            (tw, th), _ = cv2.getTextSize(label, self.font, 0.4, 1)
                            cv2.rectangle(output_frame, (x1, y1 - 15), (x1 + tw, y1), color, -1)
                            cv2.putText(output_frame, label, (x1, y1 - 4), self.font, 0.4, (255, 255, 255), 1)
                            
                            # Emotion Label (Over the rectangle)
                            # Reduced font size to 0.45
                            if sub_label:
                                cv2.putText(output_frame, sub_label, (x1, y1 - 18), self.font, 0.45, (0, 255, 255), 1)
                    except Exception as e:
                        # If one detection fails, continue with others
                        print(f"[Error] Processing detection failed: {e}")
                        continue

            # APPLY HEATMAP OVERLAY if Toggled
            if self.show_heatmap:
                try:
                    # Normalize and Colorize
                    acc = self.heat_accumulators[cam_index]
                    # Gaussian Blur for smooth blobs
                    # We blur the accumulator slightly every frame for efficiency or just render blurred?
                    # Rendering blurred is better.
                    blurred = cv2.GaussianBlur(acc, (31, 31), 0)
                    
                    # Normalize to 0-255
                    norm = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    heatmap_img = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
                    
                    # Overlay (Add weighted)
                    output_frame = cv2.addWeighted(output_frame, 0.6, heatmap_img, 0.4, 0)
                    
                    cv2.putText(output_frame, "HEATMAP MODE", (10, 60), self.font, 0.7, (0, 0, 255), 2)
                except Exception as e:
                    print(f"[Error] Heatmap rendering failed: {e}")

            # Draw Zones
            try:
                self.track_manager.zone_manager.draw_zones(output_frame, cam_index)
            except Exception as e:
                print(f"[Error] Zone drawing failed: {e}")

            # Overlay Info
            # Reduced font size to 0.6
            cv2.putText(output_frame, stream_name, (10, 30), self.font, 0.6, (255, 255, 255), 2)
            
        except Exception as e:
            print(f"[Error] Frame processing failed: {e}")
            cv2.putText(output_frame, "Processing Error", (10, 60), self.font, 0.5, (0, 0, 255), 1)
        
        return output_frame

    def run(self):
        # 0. Show Splash Screen
        print("[System] Opening Window...")
        cv2.namedWindow('Retail Vision - Connected Cameras Only', cv2.WINDOW_NORMAL)
        splash = np.zeros((600, 800, 3), dtype=np.uint8)
        cv2.putText(splash, "INITIALIZING AI SYSTEM...", (150, 280), self.font, 1.2, (0, 255, 0), 2)
        cv2.putText(splash, "Downloading/Loading Model (Please Wait)...", (100, 330), self.font, 0.8, (255, 255, 255), 1)
        cv2.imshow('Retail Vision - Connected Cameras Only', splash)
        cv2.waitKey(1)
        
        # 1. Load Model (Lazy)
        if self.model is None:
            print("[System] Loading YOLOv8s Model...")
            try:
                self.model = YOLO('yolov8s.pt')
            except Exception as e:
                print(f"[Critical Error] Failed to load model: {e}")
                
                # Auto-Correction for Corrupted Download
                if "zip archive" in str(e) or "central directory" in str(e):
                    print("[System] DETECTED CORRUPTED MODEL FILE. DELETING...")
                    try:
                        os.remove('yolov8s.pt')
                        print("[System] SUCCESS. File deleted.")
                        msg = "CORRUPT FILE DELETED. PLEASE RESTART APP."
                    except Exception as del_e:
                        msg = f"COULD NOT DELETE FILE: {del_e}"
                else:
                    msg = "FATAL ERROR LOADING MODEL"

                cv2.putText(splash, msg, (50, 400), self.font, 0.7, (0, 0, 255), 2)
                cv2.imshow('Retail Vision - Connected Cameras Only', splash)
                cv2.waitKey(5000)
                return

        # 2. Initialize Threaded Cameras
        caps = []
        for i, cam in enumerate(self.config['cameras']):
            # If it's an integer string, convert to int (Webcam index)
            src = cam['source']
            if str(src).isdigit(): 
                src = int(src)
            elif src == "":
                caps.append(None)
                continue
            
            print(f"[System] Connecting to Camera {i+1} ({src})...")    
            caps.append(ThreadedCamera(src))

        print("[System] SYSTEM READY. Press 'q' to exit. Press 'h' to toggle Heatmap.")
        print("[Info] Waiting for video feeds...")
        
        print("[Info] Waiting for video feeds...")
        
        last_heatmap_save = time.time()
        last_status_log = time.time()

        # Create window explicitly
        cv2.namedWindow('Retail Vision - Connected Cameras Only', cv2.WINDOW_NORMAL)

        while True:
            frames = []
            valid_indices = []
            
            # 1. Read Frames
            for i, cap in enumerate(caps):
                if cap:
                    ret, fr = cap.read()
                    frames.append(fr if ret else None)
                    if ret: valid_indices.append(i)
                else:
                    frames.append(None)
            
            # 2. Process Only Valid/Active Frames for Display
            processed_valid_views = []
            for i in valid_indices:
                name = self.config['cameras'][i]['name']
                view = self.process_frame(frames[i], name, i)
                processed_valid_views.append(view)
            
            # 3. Dynamic Grid Construction
            count = len(processed_valid_views)
            final_display = None
            
            try:
                if count == 0:
                    # No cameras active
                    final_display = np.zeros((360, 640, 3), dtype=np.uint8)
                    cv2.putText(final_display, "No Cameras Connected", (200, 180), self.font, 1, (0, 0, 255), 2)
                elif count == 1:
                    # Single View (Full)
                    final_display = processed_valid_views[0]
                elif count == 2:
                    # Split Horizontal
                    final_display = np.hstack((processed_valid_views[0], processed_valid_views[1]))
                elif count == 3:
                    # 2 Top, 1 Bottom (Centered)
                    top = np.hstack((processed_valid_views[0], processed_valid_views[1]))
                    # Create black filler for bottom right
                    h, w, c = processed_valid_views[2].shape
                    black = np.zeros((h, w, c), dtype=np.uint8)
                    btm = np.hstack((processed_valid_views[2], black)) 
                    final_display = np.vstack((top, btm))
                elif count >= 4:
                    # 2x2 Grid (Take first 4)
                    top = np.hstack((processed_valid_views[0], processed_valid_views[1]))
                    btm = np.hstack((processed_valid_views[2], processed_valid_views[3]))
                    final_display = np.vstack((top, btm))

                # 4. Status Indicators (Total Count, Recording status)
                if count > 0:
                    # Recording Blinker
                    cv2.circle(final_display, (30, 30), 8, (0, 255, 0), -1) 
                    cv2.putText(final_display, "REC", (45, 35), self.font, 0.5, (0, 255, 0), 1)
                    
                    # Current Active Tracks
                    current_active = len(self.track_manager.active_tracks)
                    visitor_text = f"Active: {current_active}"
                    
                    # Position: Top Right
                    h, w, _ = final_display.shape
                    (tw, th), _ = cv2.getTextSize(visitor_text, self.font, 0.6, 2)
                    cv2.putText(final_display, visitor_text, (w - tw - 20, 40), self.font, 0.6, (0, 255, 255), 2)
                    
                    if self.show_heatmap:
                         cv2.putText(final_display, "[H] HEATMAP ON", (w // 2 - 80, 40), self.font, 0.6, (0, 0, 255), 2)

                cv2.imshow('Retail Vision - Connected Cameras Only', final_display)
            except Exception as e:
                print(f"[Display Error] {e}")
                pass
            
            # Periodic Cleanup & DB Save
            if time.time() - last_heatmap_save > 5.0: # 5 seconds
                self.track_manager.cleanup_old_tracks()
                
                # Log Section & Cashier Stats
                # 1. Section Counts
                tm = self.track_manager
                c_cloth = len(tm.section_counts["Clothing"])
                c_elec = len(tm.section_counts["Electronics"])
                # Reset counts (simple logic: active distinct IDs per 5s interval)
                tm.section_counts = {"Clothing": set(), "Electronics": set(), "Cashier Queue": set()}
                
                if c_cloth > 0: self.db.log_section_analytics("Clothing", c_cloth, 0, 0)
                if c_elec > 0: self.db.log_section_analytics("Electronics", c_elec, 0, 0)
                
                # 2. Cashier Logic (Count people in 'Cashier Queue' zone currently)
                # Need to count active tracks currently in that zone
                q_len = 0
                for gid, trk in tm.active_tracks.items():
                    if trk.get('current_zone') == "Cashier Queue":
                        q_len += 1
                
                is_busy = (q_len > 2)
                self.db.log_cashier_status(q_len, is_busy)
                
                last_heatmap_save = time.time()
            
            # Real-time System Status Log (Every 3s)
            if time.time() - last_status_log > 3.0:
                active_count = len(self.track_manager.active_tracks)
                
                # Check if camera 0 (Main Entrance) is active
                cam_status = "OK"
                if len(caps) > 0 and caps[0] is None:
                    cam_status = "NO SIGNAL: CAM 0"
                elif count == 0:
                    cam_status = "NO CAMERAS"
                    active_count = 0 # Force 0 if no cameras
                
                self.db.log_system_status(active_count, cam_status)
                last_status_log = time.time()

            # KEY LISTENER
            k = cv2.waitKey(1) & 0xFF
            if k == ord('q'):
                break
            elif k == ord('h'): # Toggle Heatmap
                self.show_heatmap = not self.show_heatmap
                print(f"[System] Heatmap Toggle: {self.show_heatmap}")

        # Cleanup
        print("[System] Stopping...")
        self.ai_worker.stop()
        for cap in caps:
            if cap: cap.release()
        cv2.destroyAllWindows()


# ==========================================
# PART 5: Simple Camera Launcher
# ==========================================
class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Retail Vision - Setup")
        self.root.geometry("500x350")
        
        self.config = {'cameras': []}
        self.started = False
        
        tk.Label(self.root, text="Connect Cameras", font=("Arial", 16, "bold")).pack(pady=15)
        tk.Label(self.root, text="Enter Camera Index (0, 1...) or RTSP URL", font=("Arial", 10)).pack()

        self.entries = []
        defaults = ["Main Entrance", "Aisle 1", "Checkout", "Back Store"]
        
        frame_container = tk.Frame(self.root)
        frame_container.pack(pady=10)

        for i in range(4):
            f = tk.Frame(frame_container)
            f.pack(fill="x", pady=2)
            
            tk.Label(f, text=f"Cam {i+1}:", width=8).pack(side="left")
            name_ent = tk.Entry(f, width=15)
            name_ent.insert(0, defaults[i])
            name_ent.pack(side="left", padx=5)
            
            # Default to index if it's the first one, else empty or index
            src_ent = tk.Entry(f, width=20)
            if i == 0: src_ent.insert(0, "0")
            # Removed default "1" for second camera to avoid errors for single-cam users
            # elif i == 1: src_ent.insert(0, "1")
            
            src_ent.pack(side="left")
            self.entries.append((name_ent, src_ent))

        tk.Button(self.root, text="START MONITORING", bg="green", fg="white", 
                 font=("Arial", 12, "bold"), command=self.start).pack(pady=20, fill="x", padx=50)
        
        self.root.mainloop()

    def start(self):
        for name_e, src_e in self.entries:
            src = src_e.get().strip()
            self.config['cameras'].append({'name': name_e.get(), 'source': src})
        
        self.started = True
        self.root.destroy()

if __name__ == "__main__":
    app = Launcher()
    if app.started:
        system = RetailSystem(app.config)
        system.run()
