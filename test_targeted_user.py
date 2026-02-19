import requests
import json
import time

# Port 5001 is used because 5000 is occupied by AnyDesk
BASE_URL = "http://localhost:5001"
TARGET_PHONE = input("Enter the phone number to test alerts with (e.g. 9025267350): ").strip()
TEST_NAME = "Manual Test User"
EVENT_ID = "TEST_EVENT"

def run_targeted_test():
    print(f"--- Starting Targeted Test for Phone: {TARGET_PHONE} ---")
    
    # 1. Register the target user
    print(f"\n[Step 1] Registering {TEST_NAME} for Event {EVENT_ID}...")
    reg_data = {
        "name": TEST_NAME,
        "phone": TARGET_PHONE,
        "event_id": EVENT_ID
    }
    
    try:
        reg_res = requests.post(f"{BASE_URL}/register", json=reg_data)
        if reg_res.status_code != 200:
            print(f"FAILED: Registration returned {reg_res.status_code}")
            return
        
        user_id = reg_res.json().get("user_id")
        print(f"SUCCESS: User {TEST_NAME} (ID: {user_id}) registered.")
    except Exception as e:
        print(f"ERROR: Could not connect to app.py at {BASE_URL}. Please ensure it is running.")
        return

    # 2. Register 5 dummy users to create a crowd
    print("\n[Step 2] Creating a crowd of 5 additional users...")
    dummy_ids = []
    for i in range(1, 6):
        res = requests.post(f"{BASE_URL}/register", json={
            "name": f"Dummy {i}",
            "phone": f"900000{i:04d}",
            "event_id": EVENT_ID
        })
        if res.status_code == 200:
            dummy_ids.append(res.json().get("user_id"))
    
    # 3. Trigger Crowd Alert
    print("\n[Step 3] Positioning all users at the same coordinate to trigger threshold...")
    lat, lon = 13.0827, 80.2707  # Chennai coordinates
    
    # Update dummies
    for uid in dummy_ids:
        requests.post(f"{BASE_URL}/location", json={
            "user_id": uid,
            "latitude": lat,
            "longitude": lon
        })
    
    # Update target user
    print(f"Sending location for {TARGET_PHONE}...")
    final_res = requests.post(f"{BASE_URL}/location", json={
        "user_id": user_id,
        "latitude": lat,
        "longitude": lon
    })

    if final_res.status_code == 200:
        print("\n--- TEST COMPLETED ---")
        print(f"Target Number: {TARGET_PHONE}")
        print("Location coordinates sent successfully.")
        print("\nIMPORTANT: The background monitor checks every 5 seconds.")
        print("Please check the 'app.py' terminal output for 'Sending NORMAL_GPS alert'.")
        print("You should receive the SMS on your device shortly.")
    else:
        print(f"FAILED: final location update returned {final_res.status_code}")

if __name__ == "__main__":
    run_targeted_test()
