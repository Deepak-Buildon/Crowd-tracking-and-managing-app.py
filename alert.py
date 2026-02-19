import requests
import json
from datetime import datetime
from urllib.parse import quote

class Alertmsg:
    def __init__(self):
        # --- Telegram ---
        self.use_telegram = False
        self.telegram_bot_token = ""
        self.telegram_chat_id = ""

        # --- n8n / Generic Webhook ---
        self.use_webhook = False
        self.webhook_url = ""

        # --- WhatsApp (CallMeBot) ---
        self.use_whatsapp = False
        self.whatsapp_apikey = ""

        # --- Twilio SMS (disabled) ---
        self.use_twilio = False

    def send_alert(self, number, message):
        """
        Sends alerts through all configured channels.
        """
        print(f"--- Triggering Alert for {number} ---")
        success = False

        # 1. Telegram Alert (Free & Reliable)
        if self.use_telegram and self.telegram_bot_token and self.telegram_chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
                payload = {
                    "chat_id": self.telegram_chat_id,
                    "text": f"🚨 *CROWD ALERT*\n\nPhone: `{number}`\n\n{message}",
                    "parse_mode": "Markdown"
                }
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    print(f"✅ Telegram alert sent to chat {self.telegram_chat_id}")
                    success = True
                else:
                    print(f"Telegram Error: {resp.text}")
            except Exception as e:
                print(f"Telegram Error: {e}")

        # 2. WhatsApp Alert (via CallMeBot - Free)
        if self.use_whatsapp and self.whatsapp_apikey:
            try:
                clean_num = number.replace("+", "").replace(" ", "")
                encoded_msg = quote(message)
                url = f"https://api.callmebot.com/whatsapp.php?phone={clean_num}&text={encoded_msg}&apikey={self.whatsapp_apikey}"
                requests.get(url, timeout=10)
                print(f"✅ WhatsApp alert sent to {number}")
                success = True
            except Exception as e:
                print(f"WhatsApp Error: {e}")

        # 3. Webhook Alert (for n8n, Zapier, etc)
        if self.use_webhook and self.webhook_url:
            try:
                payload = {
                    "phone": number,
                    "message": message,
                    "channel": "whatsapp" if self.use_whatsapp else "generic",
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                resp = requests.post(self.webhook_url, json=payload, timeout=10)
                print(f"✅ Webhook (n8n) alert sent. Status: {resp.status_code}")
                success = True
            except Exception as e:
                print(f"Webhook Error: {e}")

        # 4. Local Console Alert (always active)
        print(f"📋 LOCAL LOG: [{number}] -> {message}")
        return success


if __name__ == "__main__":
    print("--- Multi-Channel Alert System Test ---")
    alert_system = Alertmsg()
    recipient_number = input("Enter recipient number: ").strip()
    alert_message = input("Enter message: ").strip()

    if recipient_number and alert_message:
        alert_system.send_alert(recipient_number, alert_message)
    else:
        print("Recipient number and message are required.")