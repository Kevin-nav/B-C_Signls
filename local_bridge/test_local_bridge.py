# test_local_bridge.py
import asyncio
import json
import uuid
import random
from asyncio import StreamReader, StreamWriter
from typing import Optional

# --- Configuration ---
# These should match the [bridge] section of your config.ini
BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 31415

# --- Message Helpers (must match the bridge's implementation) ---

async def write_message(writer: StreamWriter, data: dict):
    """Write a length-prefixed JSON message to stream."""
    try:
        payload = json.dumps(data).encode('utf-8')
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
        print(f"↗️  Sent {len(payload)} bytes to bridge.")
        print(f"   Payload: {data}")
    except Exception as e:
        print(f"❌ Error writing message: {e}")
        raise

async def read_message(reader: StreamReader) -> Optional[dict]:
    """Read a length-prefixed JSON message from stream."""
    try:
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')
        
        data = await reader.readexactly(msg_len)
        response = json.loads(data.decode('utf-8'))
        print(f"↘️  Received {msg_len} bytes from bridge.")
        print(f"   Response: {response}")
        return response
        
    except asyncio.IncompleteReadError:
        print("🔌 Connection closed by the bridge.")
    except json.JSONDecodeError as e:
        print(f"❌ Failed to decode JSON response: {e}")
    except Exception as e:
        print(f"❌ Unexpected error reading message: {e}")
    return None

# --- Main Test Function ---

async def send_test_signal(is_buy: bool = True):
    """
    Connects to the bridge, sends a single test signal, and prints the response.
    """
    print("="*70)
    print(f"▶️  Attempting to connect to bridge at {BRIDGE_HOST}:{BRIDGE_PORT}...")
    
    try:
        reader, writer = await asyncio.open_connection(BRIDGE_HOST, BRIDGE_PORT)
        print(f"✅ Connected successfully!")
    except ConnectionRefusedError:
        print(f"❌ Connection refused. Is the local_bridge.py script running?")
        print(f"   Please run 'debug_run.bat' or 'run_background.vbs' and try again.")
        return
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    try:
        # 1. Define Signal Parameters
        sym = "Volatility 75 Index"
        action = "BUY" if is_buy else "SELL"
        price = round(random.uniform(350000, 400000), 4)
        atr = random.uniform(500, 1000)
        
        # 2. Calculate SL/TP (same logic as MQL5)
        sl_multiplier = 1.5
        tp1_multiplier = 1.5
        tp2_multiplier = 3.0
        tp3_multiplier = 4.5

        if is_buy:
            sl = price - (atr * sl_multiplier)
            tp1 = price + (atr * tp1_multiplier)
            tp2 = price + (atr * tp2_multiplier)
            tp3 = price + (atr * tp3_multiplier)
        else: # SELL
            sl = price + (atr * sl_multiplier)
            tp1 = price - (atr * tp1_multiplier)
            tp2 = price - (atr * tp2_multiplier)
            tp3 = price - (atr * tp3_multiplier)

        # 3. Format the Telegram message
        direction_emoji = "🟢" if is_buy else "🔴"
        telegram_message = (
            f"{direction_emoji} *{action} SIGNAL* {direction_emoji}\n\n"
            f"┌ *Symbol:* {sym}\n"
            f"├ *Timeframe:* H1\n"
            f"├ *Entry:* `{price:.4f}`\n"
            f"├ *SL:* `{sl:.4f}`\n"
            f"├ *TP1:* `{tp1:.4f}`\n"
            f"├ *TP2:* `{tp2:.4f}`\n"
            f"└ *TP3:* `{tp3:.4f}`\n\n"
            "Zeno Wave EA v1.3"
        )

        # 4. Construct the final JSON payload
        client_id = str(uuid.uuid4())
        payload = {
            "client_msg_id": client_id,
            "type": "signal",
            "action": action,
            "symbol": sym,
            "timeframe": "H1",
            "entry": price,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "message": telegram_message,
            "allow_close": True
        }

        # 5. Send the signal and wait for a response
        print("\n--- Sending Signal ---")
        await write_message(writer, payload)
        
        print("\n--- Waiting for Response ---")
        await read_message(reader)

    except Exception as e:
        print(f"\n❌ An error occurred during communication: {e}")
    finally:
        print("\n--- Closing Connection ---")
        writer.close()
        await writer.wait_closed()
        print("="*70)


if __name__ == "__main__":
    # To run this test:
    # 1. Make sure the local_bridge.py script is running.
    # 2. Run this script from your terminal: python test_local_bridge.py
    
    # You can change this to False to test a SELL signal
    test_a_buy_signal = True
    
    asyncio.run(send_test_signal(is_buy=test_a_buy_signal))
