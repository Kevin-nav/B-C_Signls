#!/usr/bin/env python3
"""
Test script to send sample signals to your refactored trading bot.
Use this to verify the bot is working correctly before connecting MT5.
"""

import requests
import json
import time
import os
from dotenv import load_dotenv

# =====================================================================
# CONFIGURATION - Loaded from your .env file
# =====================================================================

# Load environment variables from .env file
load_dotenv()

PORT = os.getenv("PORT", 5000)
SECRET_KEY = os.getenv("WEBHOOK_SECRET_KEY")

WEBHOOK_URL = f"http://51.20.32.51:{PORT}/signal"
HEALTH_URL = f"http://51.20.32.51:{PORT}/health"
STATS_URL = f"http://51.20.32.51:{PORT}/stats"


# =====================================================================
# Test Functions
# =====================================================================

def send_signal(action: str, symbol: str, price: float, open_signal_id: int = None):
    """Send a test signal to the bot."""
    payload = {
        "secret_key": SECRET_KEY,
        "action": action,
        "symbol": symbol,
        "price": price
    }
    if open_signal_id:
        payload["open_signal_id"] = open_signal_id

    print(f"\n{'='*60}")
    print(f"Sending {action} signal for {symbol} @ {price}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"Status Code: {response.status_code}")
        if response.ok:
            print("✅ SUCCESS!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        elif response.status_code == 429:
            print("🕒 RATE LIMIT HIT!")
            print(f"   Server response: {response.text}")
        else:
            print("❌ ERROR!")
            print(f"Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ CONNECTION ERROR: {e}")
        print("   Is the main.py application running?")

def test_endpoint(url: str, name: str):
    """Test a GET endpoint like health or stats."""
    print(f"\n{'='*60}")
    print(f"Testing {name} Endpoint")
    print(f"{'='*60}")
    try:
        response = requests.get(url, timeout=5)
        print(f"Status Code: {response.status_code}")
        if response.ok:
            print(f"✅ {name} check successful!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ {name} check failed!")
    except requests.exceptions.RequestException as e:
        print(f"❌ CONNECTION ERROR: {e}")

# =====================================================================
# Test Scenarios
# =====================================================================

def test_basic_flow():
    print("\n" + "="*60)
    print("TEST SCENARIO 1: Basic Signal Flow (BUY -> SELL -> CLOSE)")
    print("="*60)
    send_signal("BUY", "EURUSD", 1.08450)
    time.sleep(1)
    send_signal("SELL", "GBPUSD", 1.26350)
    time.sleep(1)
    send_signal("CLOSE", "EURUSD", 1.08550, open_signal_id=1)

def test_rate_limiting():
    print("\n" + "="*60)
    print("TEST SCENARIO 2: Rate Limiting (MIN_SECONDS_BETWEEN_SIGNALS)")
    print("="*60)
    send_signal("BUY", "USDJPY", 149.500)
    print("\nSending another signal immediately (should be rate limited)...")
    time.sleep(1)
    send_signal("BUY", "USDJPY", 149.550)

def test_invalid_secret():
    print("\n" + "="*60)
    print("TEST SCENARIO 3: Invalid Secret Key (Should Fail with 401)")
    print("="*60)
    original_key = SECRET_KEY
    globals()["SECRET_KEY"] = "WRONG_KEY"
    send_signal("BUY", "AUDUSD", 0.65000)
    globals()["SECRET_KEY"] = original_key # Reset key

def test_invalid_action():
    print("\n" + "="*60)
    print("TEST SCENARIO 4: Invalid Action (Should Fail with 400)")
    print("="*60)
    send_signal("HOLD", "EURUSD", 1.08000)

# =====================================================================
# Main Menu
# =====================================================================

def main():
    print("--- Trading Signal Bot - Test Runner ---")
    if not SECRET_KEY or SECRET_KEY == "YOUR_SECURE_SECRET_KEY_HERE":
        print("\n⚠️ WARNING: WEBHOOK_SECRET_KEY is not set in your .env file.")
        print("   Please set it before running tests.")
        return

    while True:
        print("\nSelect a test to run:")
        print("  1. Health Check")
        print("  2. Get Statistics")
        print("  3. Send Single BUY Signal")
        print("  4. Send Single SELL Signal")
        print("  5. Send CLOSE Signal")
        print("  ---")
        print("  6. Run Basic Flow Test (BUY -> SELL -> CLOSE)")
        print("  7. Test Rate Limiting")
        print("  8. Test Invalid Secret Key (Security)")
        print("  9. Test Invalid Action (Validation)")
        print("  0. Exit")

        choice = input("\nEnter choice: ").strip()
        if choice == "1": test_endpoint(HEALTH_URL, "Health")
        elif choice == "2": test_endpoint(STATS_URL, "Stats")
        elif choice == "3": send_signal("BUY", "EURUSD", 1.08450)
        elif choice == "4": send_signal("SELL", "GBPUSD", 1.26350)
        elif choice == "5":
            try:
                sid = int(input("Enter the signal ID to close: ").strip())
                price = float(input(f"Enter the close price for signal #{sid}: ").strip())
                send_signal("CLOSE", "EURUSD", price, open_signal_id=sid)
            except ValueError:
                print("Invalid input. Please enter numbers.")
        elif choice == "6": test_basic_flow()
        elif choice == "7": test_rate_limiting()
        elif choice == "8": test_invalid_secret()
        elif choice == "9": test_invalid_action()
        elif choice == "0":
            print("\n👋 Goodbye!")
            break
        else:
            print("Invalid choice!")

if __name__ == "__main__":
    main()
