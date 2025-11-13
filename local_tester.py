# -*- coding: utf-8 -*-
# local_tester.py
# This script simulates the local_bridge to send a single, real-time test signal
# to the main AutoSig server for end-to-end testing.

import asyncio
import json
import logging
import configparser
from asyncio import StreamReader, StreamWriter
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta

# --- Basic Logging and Config ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def load_config():
    config = configparser.ConfigParser()
    config.read('test_config.ini')
    return config

CONFIG = load_config()

# --- Copied from local_bridge.py ---

mt5_initialized = False

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
}

async def initialize_mt5():
    """Initialize connection to the MetaTrader 5 terminal."""
    global mt5_initialized
    mt5_path = CONFIG.get('metatrader', 'mt5_path', fallback=None) or None
    
    if mt5_initialized:
        return True

    try:
        logging.info("Attempting to initialize MetaTrader 5...")
        if mt5_path:
            mt5_initialized = mt5.initialize(path=mt5_path)
        else:
            mt5_initialized = mt5.initialize()

        if mt5_initialized:
            logging.info("MetaTrader 5 initialized successfully.")
            account_info = mt5.account_info()
            if account_info:
                logging.info(f"Logged in to account: {account_info.login}")
            else:
                logging.warning("Not logged into a trading account.")
        else:
            logging.error(f"mt5.initialize() failed, error code = {mt5.last_error()}")
    except Exception as e:
        logging.error(f"An exception occurred during MT5 initialization: {e}")
    
    return mt5_initialized

async def get_atr(symbol: str) -> Optional[float]:
    """Fetches candles and calculates the 14-period ATR."""
    if not mt5_initialized:
        logging.error("Cannot get ATR, MT5 not initialized.")
        return None
    
    try:
        if "Crash" in symbol or "Boom" in symbol:
            timeframe_str = "M30"
        elif "Volatility" in symbol:
            timeframe_str = "M15"
        else:
            timeframe_str = 'M30' # Default for this test

        mt5_timeframe = TIMEFRAME_MAP.get(timeframe_str, mt5.TIMEFRAME_M30)
        logging.info(f"Calculating ATR for {symbol} on timeframe {timeframe_str}")

        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, 20)
        if rates is None or len(rates) < 15:
            logging.error(f"Could not get enough rates for {symbol}. Received: {len(rates) if rates else 0}")
            return None
            
        rates_df = pd.DataFrame(rates)
        rates_df['time'] = pd.to_datetime(rates_df['time'], unit='s')
        
        atr_series = rates_df.ta.atr(length=14)
        if atr_series is None or atr_series.empty:
            logging.error(f"Failed to calculate ATR for {symbol}.")
            return None
            
        latest_atr = atr_series.iloc[-2]
        logging.info(f"Calculated ATR for {symbol}: {latest_atr}")
        return latest_atr
        
    except Exception as e:
        logging.error(f"Error calculating ATR for {symbol}: {e}")
        return None

async def write_message(writer: StreamWriter, data: dict):
    """Sends a length-prefixed JSON message."""
    try:
        payload = json.dumps(data).encode()
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
    except Exception as e:
        logging.error(f"write_message error: {e}")

async def read_message(reader: StreamReader) -> Optional[dict]:
    """Reads a length-prefixed JSON message."""
    try:
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')
        data = await reader.readexactly(msg_len)
        return json.loads(data.decode())
    except asyncio.IncompleteReadError:
        logging.warning("Connection closed by peer.")
    except Exception as e:
        logging.error(f"read_message error: {e}")
    return None

# --- Main Test Logic ---

async def main():
    """Connects to MT5, generates a signal, and sends it to the AutoSig server."""
    logging.info("--- Starting Local Tester ---")
    
    if not await initialize_mt5():
        logging.error("Could not initialize MT5. Aborting test.")
        return

    # --- 1. Define Test Signal ---
    test_symbol = "Boom 500 Index"
    logging.info(f"Preparing test signal for symbol: {test_symbol}")

    # --- 2. Get Live Data ---
    tick = mt5.symbol_info_tick(test_symbol)
    atr = await get_atr(test_symbol)

    if not tick or not atr:
        logging.error("Failed to get live price or ATR. Aborting test.")
        mt5.shutdown()
        return

    current_price = tick.bid
    logging.info(f"Live data received: Price={current_price}, ATR={atr}")

    # --- 3. Connect to AutoSig Server ---
    server_conf = CONFIG['server']
    security_conf = CONFIG['security']
    host = server_conf.get('host')
    port = server_conf.getint('port')
    secret = security_conf.get('secret_key')

    try:
        logging.info(f"Connecting to AutoSig server at {host}:{port}...")
        reader, writer = await asyncio.open_connection(host, port)
    except Exception as e:
        logging.error(f"Failed to connect to AutoSig server: {e}")
        mt5.shutdown()
        return

    # --- 4. Authenticate ---
    logging.info("Authenticating with server...")
    await write_message(writer, {"secret_key": secret})
    auth_response = await read_message(reader)
    
    if not auth_response or auth_response.get("status") != "success":
        logging.error(f"Authentication failed. Server responded: {auth_response}")
        writer.close()
        await writer.wait_closed()
        mt5.shutdown()
        return
    
    logging.info("Authentication successful.")

    # --- 5. Send Signal ---
    signal_payload = {
        "action": "BUY",
        "symbol": test_symbol,
        "price": current_price,
        "atr": atr,
        "client_msg_id": "local_tester_001" # Add a mock ID
    }
    
    logging.info(f"Sending signal payload: {signal_payload}")
    await write_message(writer, signal_payload)
    
    # --- 6. Get Response ---
    signal_response = await read_message(reader)
    logging.info(f"Server responded to signal: {signal_response}")

    # --- 7. Clean up ---
    logging.info("Closing connection.")
    writer.close()
    await writer.wait_closed()
    mt5.shutdown()
    logging.info("--- Test Finished ---")


if __name__ == "__main__":
    # Ensure you have installed pandas, pandas-ta, and MetaTrader5
    # pip install pandas pandas-ta MetaTrader5
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Test interrupted by user.")
