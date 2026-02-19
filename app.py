from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import sqlite3
import math
import os
import cv2
import threading
import time
import requests as http_requests
from datetime import datetime, timedelta
from alert import Alertmsg

app = Flask(__name__)
CORS(app)

DB_NAME = "crowd.db"
yolo_model = None

# Thresholds
GPS_THRESHOLD = 5
CCTV_THRESHOLD = 3
RADIUS_METERS = 50
CHECK_INTERVAL = 5 # seconds

# Multi-Channel Alert System (n8n, Telegram, etc)
alert_system = Alertmsg()

# --- CONFIGURE YOUR ALERT CHANNELS HERE ---
# n8n Webhook (enabled)
alert_system.use_webhook = True
alert_system.webhook_url = "https://achu1211.app.n8n.cloud/webhook/crowd-alert"

# Telegram (enabled) - Bot: @CrowdAlert_YourName_bot
alert_system.use_telegram = True
alert_system.telegram_bot_token = "8542498176:AAGk5Z-_5GYIn6RGkCP73aZ8K3gywYn0vaQ"
alert_system.telegram_chat_id = "7244447138"  # Dammy

# WhatsApp via CallMeBot (disabled - no key yet)
alert_system.use_whatsapp = False
alert_system.whatsapp_apikey = ""
# ------------------------------------------

# Global states
CAMERA_PERSON_COUNT = 0
LAST_CAMERA_UPDATE = None
GLOBAL_CROWDED_USERS = set()
GLOBAL_RED_ZONES = []

# Camera Sources (Add your IP Camera URL here)
camera_sources = [0, "http://100.104.168.30:8080/video"]

def generate_frames():
    global CAMERA_PERSON_COUNT, LAST_CAMERA_UPDATE
    
    cap = None
    for src in camera_sources:
        temp_cap = cv2.VideoCapture(src)
        if temp_cap.isOpened():
            cap = temp_cap
            break
            
    if not cap:
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')
        return

    while True:
        if cap is None:
            break
        success, frame = cap.read()
        if not success:
            break
        
        # YOLO detection
        count = 0
        if yolo_model:
            results = yolo_model(frame, conf=0.4, verbose=False)
            for r in results:
                if hasattr(r, 'boxes') and r.boxes is not None:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        if yolo_model.names[cls] == "person":
                            count = count + 1
            CAMERA_PERSON_COUNT = count
            LAST_CAMERA_UPDATE = datetime.now().strftime('%H:%M:%S')

        # Add visual count to frame
        cv2.putText(frame, f"CCTV COUNT: {count}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    if cap is not None:
        cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def haversine(lat1, lon1, lat2, lon2):
    R = 6371 # Earth radius in km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c * 1000 # returns meters

# Initialize YOLO
try:
    from ultralytics import YOLO
    if os.path.exists("yolov8n.pt"):
        yolo_model = YOLO("yolov8n.pt")
    else:
        print("Warning: yolov8n.pt not found. CCTV detection disabled.")
except ImportError:
    print("Warning: ultralytics not installed. CCTV detection disabled.")

def send_bulk_alert(event_id, message, alert_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if we already sent an alert for this event in the last 5 minutes
    cursor.execute('''
        SELECT timestamp FROM Alerts 
        WHERE event_id = ? AND alert_type = ? 
        ORDER BY timestamp DESC LIMIT 1
    ''', (event_id, alert_type))
    last_alert = cursor.fetchone()
    
    if last_alert:
        last_time = datetime.strptime(last_alert['timestamp'], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last_time).total_seconds() < 300: # 5 minute cooldown
            conn.close()
            return
    
    # Send INDIVIDUALLY to all registered users of this event
    cursor.execute('SELECT phone, telegram_chat_id FROM Users WHERE event_id = ?', (event_id,))
    users = cursor.fetchall()
    
    for user in users:
        phone = user['phone']
        t_chat_id = user['telegram_chat_id']
        sms_num = phone if phone.startswith('+') else f"+91{phone}"
        print(f"Sending {alert_type} alert to {sms_num}")
        
        # Send individual Telegram if user has linked their account
        if t_chat_id:
            try:
                tg_url = f"https://api.telegram.org/bot{alert_system.telegram_bot_token}/sendMessage"
                http_requests.post(tg_url, json={
                    "chat_id": t_chat_id,
                    "text": f"🚨 *CROWD ALERT*\n\n{message}",
                    "parse_mode": "Markdown"
                }, timeout=5)
                print(f"  ✅ Telegram sent to user chat {t_chat_id}")
            except Exception as te:
                print(f"  Telegram send error: {te}")
        else:
            # Fallback: use main alert_system (sends to admin + webhook)
            alert_system.send_alert(sms_num, message)
    
    # Log alert
    cursor.execute('INSERT INTO Alerts (event_id, alert_sent, alert_type) VALUES (?, 1, ?)', (event_id, alert_type))
    conn.commit()
    conn.close()

def monitor_crowd():
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 1. Check GPS Thresholds
            # Get latest location for all active users
            cursor.execute('''
                SELECT u.event_id, l.user_id, l.latitude, l.longitude 
                FROM Locations l
                JOIN Users u ON l.user_id = u.id
                WHERE l.timestamp >= datetime('now', '-1 minute')
                GROUP BY l.user_id
            ''')
            active_users = cursor.fetchall()
            
            # Group by event
            events = {}
            for u in active_users:
                ev = u['event_id']
                if ev not in events: events[ev] = []
                events[ev].append(u)
            
            # Update globals for dashboard
            all_crowded = set()
            all_red_zones = []
            for event_id, users in events.items():
                crowded_users_in_event = set()
                red_zones_in_event = []
                
                for u1 in users:
                    cluster = []
                    for u2 in users:
                        dist = haversine(u1['latitude'], u1['longitude'], u2['latitude'], u2['longitude'])
                        if dist <= RADIUS_METERS:
                            cluster.append(u2['user_id'])
                    
                    count = len(cluster)
                    if count >= GPS_THRESHOLD:
                        for uid in cluster:
                            crowded_users_in_event.add(uid)
                        red_zones_in_event.append({"lat": u1['latitude'], "lon": u1['longitude'], "count": count})
                
                all_crowded.update(crowded_users_in_event)
                all_red_zones.extend(red_zones_in_event)

                max_cluster = 0
                if red_zones_in_event:
                    max_cluster = max(z['count'] for z in red_zones_in_event)
                
                # Critical Alert (Threshold + 3 = 8)
                if max_cluster >= (GPS_THRESHOLD + 3):
                    msg = "CRITICAL ALERT 🚨\nCrowd is heavily overcrowded. Immediate action required."
                    send_bulk_alert(event_id, msg, "CRITICAL_GPS")
                # Normal Alert (Threshold = 5)
                elif max_cluster >= GPS_THRESHOLD:
                    msg = "BE SAFE: You are in a heavy crowd. Please move somewhere safe. [Your life is important to us]"
                    send_bulk_alert(event_id, msg, "NORMAL_GPS")

            global GLOBAL_CROWDED_USERS, GLOBAL_RED_ZONES
            GLOBAL_CROWDED_USERS = all_crowded
            GLOBAL_RED_ZONES = all_red_zones

            # 2. Check CCTV Global Threshold (Applied to all active events)
            if CAMERA_PERSON_COUNT >= (CCTV_THRESHOLD + 3):
                msg = "CRITICAL ALERT 🚨 (CCTV)\nCrowd is heavily overcrowded. Immediate action required."
                for ev in events.keys():
                    send_bulk_alert(ev, msg, "CRITICAL_CCTV")
            elif CAMERA_PERSON_COUNT >= CCTV_THRESHOLD:
                msg = "ALERT ⚠️ (CCTV)\nCrowd limit exceeded. Please take necessary action."
                for ev in events.keys():
                    send_bulk_alert(ev, msg, "NORMAL_CCTV")

            conn.close()
        except Exception as e:
            print(f"Monitor error: {e}")
        
        time.sleep(CHECK_INTERVAL)

# --- Telegram Bot Auto-Linker ---
# Listens for incoming messages, if user sends their registered phone number
# the bot links their Telegram chat to their account in the database.
TELEGRAM_BOT_TOKEN = "8542498176:AAGk5Z-_5GYIn6RGkCP73aZ8K3gywYn0vaQ"
TELEGRAM_POLL_OFFSET = 0

def telegram_bot_listener():
    global TELEGRAM_POLL_OFFSET
    print("✅ Telegram bot listener started. Waiting for users to link their phones...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": TELEGRAM_POLL_OFFSET, "timeout": 10}
            resp = http_requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                time.sleep(5)
                continue

            data = resp.json()
            for update in data.get("result", []):
                TELEGRAM_POLL_OFFSET = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()
                
                if not chat_id or not text:
                    continue
                
                # Clean phone from user input
                phone_input = text.replace("+91", "").replace("+", "").replace(" ", "").strip()
                
                # Check if it's a /start command
                if text == "/start":
                    reply = (
                        "👋 *Welcome to Crowd Alert Bot!*\n\n"
                        "To receive personal crowd alerts, send me your *registered phone number*.\n"
                        "Example: `9025267350`\n\n"
                        "Once linked, you'll get alerts directly here when crowds are detected at your event! 🚨"
                    )
                    http_requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"}
                    )
                    continue

                # Try to match phone number in DB
                if phone_input.isdigit() and len(phone_input) >= 10:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    # Look for last 10 digits match
                    cursor.execute("SELECT id, name FROM Users WHERE phone LIKE ?", (f"%{phone_input[-10:]}",))
                    user = cursor.fetchone()
                    
                    if user:
                        cursor.execute("UPDATE Users SET telegram_chat_id = ? WHERE id = ?", (chat_id, user["id"]))
                        conn.commit()
                        conn.close()
                        name = user["name"]
                        print(f"✅ Telegram linked: {name} ({phone_input}) → chat {chat_id}")
                        http_requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": (
                                    f"✅ *Linked Successfully, {name}!*\n\n"
                                    f"Phone: `{phone_input}`\n"
                                    "You will now receive *individual crowd alerts* directly here whenever crowd density exceeds the threshold at your event.\n\n"
                                    "Stay safe! 🙏"
                                ),
                                "parse_mode": "Markdown"
                            }
                        )
                    else:
                        conn.close()
                        http_requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": (
                                    f"❌ Phone number `{phone_input}` not found.\n\n"
                                    "Please register first at the event registration page, then send your phone number here."
                                ),
                                "parse_mode": "Markdown"
                            }
                        )
        except Exception as e:
            print(f"Telegram listener error: {e}")
            time.sleep(5)

# Start background threads
threading.Thread(target=monitor_crowd, daemon=True).start()
threading.Thread(target=telegram_bot_listener, daemon=True).start()

# --- Routes ---
@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/register_page')
def register_page():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    event_id = data.get('event_id', 'E01')
    telegram_chat_id = data.get('telegram_chat_id', None)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Add telegram_chat_id column if not exists
    cursor.execute("PRAGMA table_info(Users)")
    cols = [c['name'] for c in cursor.fetchall()]
    if 'telegram_chat_id' not in cols:
        cursor.execute('ALTER TABLE Users ADD COLUMN telegram_chat_id TEXT')
    cursor.execute('INSERT INTO Users (name, phone, event_id, telegram_chat_id) VALUES (?, ?, ?, ?)', (name, phone, event_id, telegram_chat_id))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"user_id": user_id, "status": "success"})

@app.route('/location', methods=['POST'])
def log_location():
    data = request.json
    user_id = data.get('user_id')
    lat = data.get('latitude')
    lon = data.get('longitude')
    
    if not user_id or lat is None or lon is None:
        return jsonify({"error": "Missing data"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO Locations (user_id, latitude, longitude) VALUES (?, ?, ?)', (user_id, lat, lon))
    conn.commit()
    conn.close()
    
    is_crowded = user_id in GLOBAL_CROWDED_USERS
    return jsonify({
        "status": "logged",
        "is_crowded": is_crowded,
        "crowd_alert": is_crowded
    })

@app.route('/upload-frame', methods=['POST'])
def upload_frame():
    global CAMERA_PERSON_COUNT, LAST_CAMERA_UPDATE
    import base64
    import numpy as np
    try:
        data = request.json
        image_data = data.get('image')
        header, encoded = image_data.split(",", 1)
        decoded = base64.b64decode(encoded)
        nparr = np.frombuffer(decoded, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        count = 0
        if yolo_model:
            results = yolo_model(frame, conf=0.4, verbose=False)
            for r in results:
                if hasattr(r, 'boxes') and r.boxes is not None:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        if yolo_model.names[cls] == "person":
                            count = count + 1
            CAMERA_PERSON_COUNT = count
            LAST_CAMERA_UPDATE = datetime.now().strftime('%H:%M:%S')
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/current-locations')
def get_current_locations():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.name, u.phone, l.latitude, l.longitude, MAX(l.timestamp) as last_seen
        FROM Locations l
        JOIN Users u ON l.user_id = u.id
        WHERE l.timestamp >= datetime('now', '-2 minute')
        GROUP BY l.user_id
    ''')
    active_users = cursor.fetchall()
    
    users_data = []
    for u in active_users:
        users_data.append({
            "id": u['id'], "name": u['name'], "phone": u['phone'],
            "latitude": u['latitude'], "longitude": u['longitude'],
            "is_crowded": u['id'] in GLOBAL_CROWDED_USERS
        })
    
    cursor.execute('SELECT * FROM Alerts ORDER BY timestamp DESC LIMIT 5')
    recent_alerts = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({
        "users": users_data,
        "total_active": len(users_data),
        "camera_count": CAMERA_PERSON_COUNT,
        "recent_alerts": recent_alerts,
        "red_zones": GLOBAL_RED_ZONES
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
