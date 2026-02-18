# 🚀 Crowd Management & Monitor System

A professional, real-time crowd tracking and management application using **Python Flask**, **YOLOv8 AI**, and **Google Maps**.

## 📁 Project Structure

- 🧠 **Backend (`app.py`)**: Handles AI processing, database management, and SMS alerts.
- 🎨 **Dashboard (`templates/`)**: Flask-based admin interface.
- 🌐 **Static Frontend (`public/`)**: Optimized version for Netlify hosting.
- 📱 **Mobile Support (`android_client/`)**: Source code for the Android tracking app.

---

## 🚀 How to Launch (The "Automatic" Way)

I have configured the project for **Zero-Config Deployment**.

### 1. The Backend (CCTV & AI) - Host on Render
1. Go to [Render Blueprints](https://dashboard.render.com/blueprints).
2. Connect this GitHub repository.
3. Render will use the `render.yaml` file to **automatically** set up the Free Tier server.
4. Copy the URL Render gives you (e.g., `https://crowd-monitor.onrender.com`).

### 2. The Frontend (Dashboard) - Host on Netlify
1. Go to [Netlify](https://app.netlify.com/).
2. Drag and drop the `public` folder OR connect your GitHub.
3. Netlify will use the `netlify.toml` file to **automatically** configure the site.
4. Open your new `.netlify.app` link.
5. **Final Step**: Enter your Render URL when prompted to sync the systems.

---

## 🛠 Local Setup (For Development)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run the App**:
   ```bash
   python app.py
   ```
3. **Access Internal Dashboard**: `http://localhost:5000/dashboard`

---

## 🔥 Key Features
- **YOLOv8 CCTV**: Real-time person counting from IP Cameras or Webcams.
- **GPS Zoning**: Automatic detection of heavy crowd clusters on a live map.
- **Smart SMS**: Directly alerts users in danger zones via Twilio.
- **Reboot Button**: Instant CCTV stream recovery button on the dashboard.

---
*Created with ❤️ for Crowd Safety.*
