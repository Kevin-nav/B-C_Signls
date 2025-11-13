# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import configparser
import os
from datetime import datetime
from asyncio import StreamReader, StreamWriter, Queue
from typing import Optional, Dict

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta

# --- Config ---
def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

CONFIG = load_config()

# --- Logging ---
def setup_logging():
    """Configures logging to both console and a daily rotating file."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    log_filename = os.path.join(log_dir, f"bridge_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    log_format = '[%(asctime)s] %(levelname)s: %(name)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Get the root logger and set its level
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clear any previous handlers to prevent duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # Create file handler for daily logs
    file_handler = logging.FileHandler(log_filename, mode='a')
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    logger.addHandler(file_handler)
    
    # Create console handler for real-time output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    logger.addHandler(console_handler)
    
    logging.info("Logging initialized with daily file rotation.")

# --- Global State ---
vps_reader: Optional[StreamReader] = None
vps_writer: Optional[StreamWriter] = None
vps_send_queue = Queue()
client_map: Dict[str, StreamWriter] = {}  # map client_msg_id -> EA writer
mt5_initialized = False

# --- MT5 Timeframe Mapping ---
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M2": mt5.TIMEFRAME_M2, "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4, "M5": mt5.TIMEFRAME_M5, "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10, "M12": mt5.TIMEFRAME_M12, "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20, "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2, "H3": mt5.TIMEFRAME_H3, "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6, "H8": mt5.TIMEFRAME_H8, "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
}

# --- MT5 Functions ---
async def initialize_mt5():
    """Initialize connection to the MetaTrader 5 terminal."""
    global mt5_initialized
    mt5_path = CONFIG.get('metatrader', 'mt5_path', fallback=None)
    
    while not mt5_initialized:
        try:
            logging.info("Attempting to initialize MetaTrader 5...")
            if mt5_path:
                mt5_initialized = mt5.initialize(path=mt5_path)
            else:
                mt5_initialized = mt5.initialize()

            if mt5_initialized:
                logging.info("MetaTrader 5 initialized successfully.")
                version = mt5.version()
                logging.info(f"MT5 Version: {version}")
                
                account_info = mt5.account_info()
                if account_info:
                    logging.info(f"Logged in to account: {account_info.login} on {account_info.server}")
                else:
                    logging.warning("Not logged into a trading account.")
            else:
                logging.error(f"mt5.initialize() failed, error code = {mt5.last_error()}")
                logging.info("Retrying in 15 seconds...")
                await asyncio.sleep(15)
        except Exception as e:
            logging.error(f"An exception occurred during MT5 initialization: {e}")
            logging.info("Retrying in 15 seconds...")
            await asyncio.sleep(15)

async def get_atr(symbol: str) -> Optional[float]:
    """
    Fetches candles and calculates the 14-period ATR.
    The timeframe is determined dynamically based on the symbol name.
    """
    if not mt5_initialized:
        logging.error("Cannot get ATR, MT5 not initialized.")
        return None
    
    try:
        # Determine timeframe based on symbol name
        if "Crash" in symbol or "Boom" in symbol:
            timeframe_str = "M30"
        elif "Volatility" in symbol:
            timeframe_str = "M15"
        else:
            # Fallback to config for other symbols (Forex, etc.)
            timeframe_str = CONFIG.get('metatrader', 'atr_timeframe', fallback='M30').upper()

        mt5_timeframe = TIMEFRAME_MAP.get(timeframe_str, mt5.TIMEFRAME_M30)
        logging.info(f"Calculating ATR for {symbol} on timeframe {timeframe_str}")

        # Fetch 20 candles to ensure enough data for calculation
        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, 20)
        if rates is None or len(rates) < 15:
            logging.error(f"Could not get enough rates for {symbol} on {timeframe_str}. Received: {len(rates) if rates else 0}")
            return None
            
        rates_df = pd.DataFrame(rates)
        rates_df['time'] = pd.to_datetime(rates_df['time'], unit='s')
        
        # Calculate ATR using pandas_ta
        atr_series = rates_df.ta.atr(length=14)
        if atr_series is None or atr_series.empty:
            logging.error(f"Failed to calculate ATR for {symbol}.")
            return None
            
        # Get the latest ATR value (from the second to last candle, as the last one is live and incomplete)
        latest_atr = atr_series.iloc[-2]
        logging.info(f"Calculated ATR for {symbol} on {timeframe_str}: {latest_atr}")
        return latest_atr
        
    except Exception as e:
        logging.error(f"Error calculating ATR for {symbol}: {e}")
        return None

# --- Message helpers ---
async def read_message(reader: StreamReader) -> Optional[dict]:
    try:
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')
        if msg_len > 4 * 1024 * 1024:
            logging.error(f"Message too large ({msg_len} bytes).")
            return None
        data = await reader.readexactly(msg_len)
        return json.loads(data.decode())
    except asyncio.IncompleteReadError:
        logging.warning("Connection closed by peer.")
    except Exception as e:
        logging.error(f"read_message error: {e}")
    return None

async def write_message(writer: StreamWriter, data: dict):
    try:
        payload = json.dumps(data).encode()
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
    except Exception as e:
        logging.error(f"write_message error: {e}")

# --- VPS connection ---
async def vps_client_handler():
    global vps_reader, vps_writer
    host = CONFIG.get('server', 'vps_host')
    port = CONFIG.getint('server', 'vps_port')
    secret = CONFIG.get('security', 'secret_key')
    heartbeat_interval = CONFIG.getint('timing', 'heartbeat_interval', fallback=30)

    while True:
        try:
            logging.info(f"Connecting to VPS {host}:{port} ...")
            vps_reader, vps_writer = await asyncio.open_connection(host, port)
            logging.info("Connected to VPS. Authenticating...")
            await write_message(vps_writer, {"secret_key": secret})
            resp = await read_message(vps_reader)

            if resp and resp.get("status") == "success":
                logging.info("Authenticated with VPS.")
                await asyncio.gather(
                    send_to_vps_loop(vps_writer, heartbeat_interval),
                    receive_from_vps_loop(vps_reader)
                )
            else:
                logging.error(f"Auth failed: {resp}")
        except Exception as e:
            logging.error(f"VPS connection error: {e}")
        finally:
            if vps_writer:
                vps_writer.close()
                await vps_writer.wait_closed()
            vps_reader = vps_writer = None
            logging.info("Reconnecting to VPS in 10s...")
            await asyncio.sleep(10)

async def send_to_vps_loop(writer: StreamWriter, heartbeat_interval: int):
    while True:
        try:
            msg = await asyncio.wait_for(vps_send_queue.get(), timeout=heartbeat_interval)
            await write_message(writer, msg)
            vps_send_queue.task_done()
            logging.info(f"Forwarded signal to VPS: {msg}")
        except asyncio.TimeoutError:
            await write_message(writer, {"type": "ping"})
            logging.info("Sent heartbeat to VPS.")
        except Exception as e:
            logging.error(f"send_to_vps_loop error: {e}")
            break

async def receive_from_vps_loop(reader: StreamReader):
    while True:
        resp = await read_message(reader)
        if not resp:
            break

        if resp.get("type") == "pong":
            logging.info("Received pong from VPS.")
            continue

        logging.info(f"Received from VPS: {resp}")

        # Relay confirmation to EA if applicable
        cid = resp.get("client_msg_id") or resp.get("open_client_msg_id")
        if cid and cid in client_map:
            try:
                ea_writer = client_map[cid]
                await write_message(ea_writer, resp)
                logging.info(f"Relayed VPS confirmation to EA for {cid}")
            except Exception as e:
                logging.warning(f"Failed to relay to EA {cid}: {e}")

# --- Local EA server ---
async def handle_ea_client(reader: StreamReader, writer: StreamWriter):
    peer = writer.get_extra_info("peername")
    logging.info(f"EA connected: {peer}")

    try:
        while True:
            msg = await read_message(reader)
            if not msg:
                break

            logging.info(f"From EA: {msg}")

            # Handle pings from the EA directly instead of forwarding
            if msg.get("type") == "ping":
                await write_message(writer, {"type": "pong"})
                logging.info("Responded to EA ping with pong.")
                continue

            # --- ATR Enrichment ---
            action = msg.get("action", "").upper()
            if action in ["BUY", "SELL"]:
                symbol = msg.get("symbol")
                if symbol:
                    atr_value = await get_atr(symbol)
                    if atr_value is not None:
                        msg["atr"] = atr_value
                        logging.info(f"Enriched signal with ATR={atr_value}")
                    else:
                        logging.warning(f"Could not get ATR for {symbol}. Sending signal without it.")
                else:
                    logging.warning("Signal message is missing 'symbol' field.")
            # --- End ATR Enrichment ---

            # Map the client_msg_id to this specific EA client writer
            cid = msg.get("client_msg_id")
            if cid:
                client_map[cid] = writer

            # Forward the signal to the VPS if connected
            if vps_writer:
                await vps_send_queue.put(msg)
                # NOTE: We no longer send an immediate ACK. The EA will wait for the real response.
            else:
                err = {"status": "error", "message": "Bridge not connected to VPS."}
                await write_message(writer, err)

    except Exception as e:
        logging.error(f"EA client error: {e}")
    finally:
        # Clean up the client_map to prevent memory leaks when a client disconnects
        keys_to_remove = [key for key, val in client_map.items() if val == writer]
        for key in keys_to_remove:
            del client_map[key]
        logging.info(f"EA disconnected: {peer}. Cleaned up {len(keys_to_remove)} message IDs.")
        writer.close()
        await writer.wait_closed()

async def start_local_server_with_retry():
    local_host = CONFIG.get('bridge', 'local_host', fallback='127.0.0.1')
    local_port = CONFIG.getint('bridge', 'local_port', fallback=5050)

    while True:
        try:
            server = await asyncio.start_server(handle_ea_client, local_host, local_port)
            logging.info(f"Local bridge started. Listening for MQL5 EA on {local_host}:{local_port}")
            async with server:
                await server.serve_forever()
        except OSError as e:
            logging.error(f"Failed to bind to {local_host}:{local_port}: {e}. Retrying in 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            logging.error(f"Unexpected error in EA server: {e}")
            await asyncio.sleep(10)

async def main():
    setup_logging()
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Start MT5 initialization in the background
    asyncio.create_task(initialize_mt5())
    
    # Start the main application tasks
    vps_task = asyncio.create_task(vps_client_handler())
    server_task = asyncio.create_task(start_local_server_with_retry())
    
    await asyncio.gather(vps_task, server_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bridge shutting down.")
    finally:
        if mt5_initialized:
            mt5.shutdown()
            logging.info("MetaTrader 5 connection shut down.")