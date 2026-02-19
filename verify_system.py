import requests
import time

BASE_URL = "http://localhost:5000"

def run_system_test():
    print("--- Starting System Integration Test ---")
    
    # 1. Test Registration
    print("\n[Step 1] Testing User Registration...")
    reg_data = {
        "name": "Test User",
        "phone": "9876543210"  # 10-digit sample
    }
    try:
        reg_response = requests.post(f"{BASE_URL}/register", json=reg_data)
        if reg_response.status_code == 200:
            user_id = reg_response.json().get("user_id")
            print(f"SUCCESS: User registered with ID {user_id}")
            print(f"Server Message: {reg_response.json().get('message')}")
        else:
            print(f"FAILED: Registration returned {reg_response.status_code}")
            return
    except Exception as e:
        print(f"ERROR: Could not connect to server at {BASE_URL}. Is app.py running?")
        return

    # 2. Test Crowd Alert (Threshold is 5)
    print("\n[Step 2] Testing Crowd Alert Logic...")
    print("Registering 5 more simulated users to create a crowd...")
    
    other_users = []
    for i in range(1, 6):
        res = requests.post(f"{BASE_URL}/register", json={
            "name": f"Simulated {i}",
            "phone": f"900000000{i}"
        })
        other_users.append(res.json().get("user_id"))

    # Place everyone at the same spot
    lat, lon = 12.9716, 77.5946
    
    print(f"Updating locations for all {len(other_users) + 1} users to coordinate ({lat}, {lon})...")
    
    # Update other users first
    for uid in other_users:
        requests.post(f"{BASE_URL}/location", json={
            "user_id": uid,
            "latitude": lat,
            "longitude": lon
        })

    # Update our main test user - this should trigger the 'is_crowded' alert in the response
    final_res = requests.post(f"{BASE_URL}/location", json={
        "user_id": user_id,
        "latitude": lat,
        "longitude": lon
    })

    if final_res.status_code == 200:
        data = final_res.json()
        print(f"SUCCESS: Server responded to location update.")
        print(f"Crowd Alert Status: {data.get('crowd_alert')}")
        if data.get('crowd_alert'):
            print(f"Alert Message: {data.get('message')}")
            print(f"Exit Link: {data.get('exit_link')}")
            print("\nVERIFICATION: The server should have logged 'Sending heavy crowd alert' in its terminal.")
        else:
            print("FAILURE: Crowd was not detected even with 6 users at the same spot.")
    else:
        print(f"FAILED: Location update returned {final_res.status_code}")

    # 3. Verify Dashboard Data
    print("\n[Step 3] Verifying Dashboard Data...")
    status_res = requests.get(f"{BASE_URL}/current-locations")
    if status_res.status_code == 200:
        dash_data = status_res.json()
        print(f"Total Active Users: {dash_data.get('total_active')}")
        print(f"Active Crowd Zones: {dash_data.get('crowd_zones')}")
        if dash_data.get('crowd_zones') > 0:
            print("Verified: Dashboard reflects the crowd zone.")
    
    print("\n--- Test Completed ---")
    print("Check the 'app.py' terminal for Twilio SMS logs.")

if __name__ == "__main__":
    run_system_test()
