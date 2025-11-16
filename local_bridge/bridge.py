# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import configparser
import os
import sys
from datetime import datetime
from asyncio import StreamReader, StreamWriter, Queue
from typing import Optional, Dict

# --- Startup Diagnostics ---
def print_startup_info():
    """Print diagnostic information at startup"""
    print("\n" + "="*70)
    print("LOCAL BRIDGE - STARTUP DIAGNOSTICS")
    print("="*70)
    print(f"Python Version: {sys.version}")
    print(f"Current Directory: {os.getcwd()}")
    print(f"Script Location: {os.path.abspath(__file__)}")
    print(f"Config File Exists: {os.path.exists('config.ini')}")
    if os.path.exists('config.ini'):
        print(f"Config File Size: {os.path.getsize('config.ini')} bytes")
    print(f"Logs Directory Exists: {os.path.exists('logs')}")
    print("="*70 + "\n")

# --- Config with Validation ---
def load_config():
    """Load and validate configuration file with detailed error messages"""
    config = configparser.ConfigParser()
    config_file = 'config.ini'
    
    # Check if config file exists
    if not os.path.exists(config_file):
        error_msg = f"""
{'='*70}
CRITICAL ERROR: Configuration file not found!
{'='*70}
Expected location: {os.path.abspath(config_file)}
Current directory: {os.getcwd()}

Please ensure config.ini is in the same directory as bridge.py

Press Ctrl+C to exit...
{'='*70}
"""
        print(error_msg)
        logging.critical(f"Config file not found: {config_file}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Try to read config file
    try:
        files_read = config.read(config_file)
        if not files_read:
            raise ValueError("Config file exists but could not be read")
        logging.info(f"Successfully loaded config from: {config_file}")
    except Exception as e:
        error_msg = f"""
{'='*70}
CRITICAL ERROR: Failed to parse configuration file!
{'='*70}
Error: {e}

The config.ini file may be corrupted or have syntax errors.
Please check the file format.

Press Ctrl+C to exit...
{'='*70}
"""
        print(error_msg)
        logging.critical(f"Failed to parse config: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Validate required sections and keys
    required_config = {
        'server': ['vps_host', 'vps_port'],
        'bridge': ['local_host', 'local_port'],
        'security': ['secret_key'],
        'timing': ['heartbeat_interval']
    }
    
    missing = []
    for section, keys in required_config.items():
        if not config.has_section(section):
            missing.append(f"[{section}] - entire section missing")
        else:
            for key in keys:
                if not config.has_option(section, key):
                    missing.append(f"[{section}] {key}")
    
    if missing:
        error_msg = f"""
{'='*70}
CRITICAL ERROR: Missing required configuration values!
{'='*70}
Missing items:
"""
        for item in missing:
            error_msg += f"  - {item}\n"
        error_msg += f"""
Please add these to your config.ini file.

Press Ctrl+C to exit...
{'='*70}
"""
        print(error_msg)
        logging.critical(f"Missing config values: {missing}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Validate data types
    try:
        vps_port = config.getint('server', 'vps_port')
        local_port = config.getint('bridge', 'local_port')
        heartbeat = config.getint('timing', 'heartbeat_interval')
        
        if not (1 <= vps_port <= 65535):
            raise ValueError(f"vps_port must be between 1-65535, got {vps_port}")
        if not (1 <= local_port <= 65535):
            raise ValueError(f"local_port must be between 1-65535, got {local_port}")
        if heartbeat < 10:
            raise ValueError(f"heartbeat_interval should be at least 10 seconds, got {heartbeat}")
            
        logging.info("Configuration validation successful")
    except ValueError as e:
        error_msg = f"""
{'='*70}
CRITICAL ERROR: Invalid configuration values!
{'='*70}
Error: {e}

Please check your config.ini for correct data types and ranges.

Press Ctrl+C to exit...
{'='*70}
"""
        print(error_msg)
        logging.critical(f"Config validation error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    return config

# --- Logging Setup ---
def setup_logging():
    """Configures logging to both console and a daily rotating file."""
    log_dir = "logs"
    
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Could not create logs directory: {e}")
        print(f"Attempted path: {os.path.abspath(log_dir)}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    log_filename = os.path.join(log_dir, f"bridge_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    log_format = '[%(asctime)s] %(levelname)s: %(name)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Get the root logger and set its level
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clear any previous handlers to prevent duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()
    
    try:
        # Create file handler for daily logs
        file_handler = logging.FileHandler(log_filename, mode='a', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        logger.addHandler(file_handler)
        
        # Create console handler for real-time output
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        logger.addHandler(console_handler)
        
        logging.info("="*70)
        logging.info("LOCAL BRIDGE STARTED")
        logging.info("="*70)
        logging.info(f"Log file: {log_filename}")
    except Exception as e:
        print(f"ERROR: Could not setup logging: {e}")
        input("Press Enter to exit...")
        sys.exit(1)

# --- Status File for Monitoring ---
def write_status(status: str, details: str = ""):
    """Write current status to file for external monitoring"""
    try:
        with open('bridge_status.txt', 'w') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp}|{status}|{details}\n")
    except Exception as e:
        logging.warning(f"Could not write status file: {e}")

# Initialize after logging is set up
CONFIG = None

# --- Global State ---
vps_reader: Optional[StreamReader] = None
vps_writer: Optional[StreamWriter] = None
vps_send_queue = Queue()
client_map: Dict[str, StreamWriter] = {}

# --- Message helpers ---
async def read_message(reader: StreamReader) -> Optional[dict]:
    """Read a length-prefixed JSON message from stream"""
    try:
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')
        
        # Sanity check on message size
        if msg_len > 10 * 1024 * 1024:  # 10MB limit
            logging.error(f"Message size too large: {msg_len} bytes. Possible corruption.")
            return None
            
        if msg_len == 0:
            logging.warning("Received message with zero length")
            return None
            
        data = await reader.readexactly(msg_len)
        return json.loads(data.decode('utf-8'))
        
    except asyncio.IncompleteReadError as e:
        logging.debug(f"Connection closed by peer (incomplete read): {e}")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON message: {e}")
    except Exception as e:
        logging.error(f"Unexpected error reading message: {e}", exc_info=True)
    return None

async def write_message(writer: StreamWriter, data: dict):
    """Write a length-prefixed JSON message to stream"""
    try:
        payload = json.dumps(data).encode('utf-8')
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
    except ConnectionResetError:
        logging.warning("Connection reset while writing message")
        raise
    except Exception as e:
        logging.error(f"Error writing message: {e}", exc_info=True)
        raise

# --- VPS connection ---
async def vps_client_handler():
    """Maintain persistent connection to VPS with automatic reconnection
    
    This function will NEVER stop trying to reconnect to the VPS.
    Even if the VPS is down for hours, the bridge will keep retrying.
    The EA server continues accepting signals during VPS downtime.
    """
    global vps_reader, vps_writer
    host = CONFIG.get('server', 'vps_host')
    port = CONFIG.getint('server', 'vps_port')
    secret = CONFIG.get('security', 'secret_key')
    heartbeat_interval = CONFIG.getint('timing', 'heartbeat_interval', fallback=30)
    
    consecutive_failures = 0
    max_reconnect_delay = 60  # Maximum 60 seconds between retries

    # Infinite reconnection loop
    while True:
        try:
            logging.info(f"Connecting to VPS at {host}:{port}...")
            if consecutive_failures > 0:
                logging.info(f"(Connection attempt after {consecutive_failures} failure(s))")
            write_status("CONNECTING_VPS", f"{host}:{port}")
            
            # Try to establish connection
            vps_reader, vps_writer = await asyncio.open_connection(host, port)
            logging.info("✓ Connected to VPS. Authenticating...")
            
            # Send authentication
            await write_message(vps_writer, {"secret_key": secret})
            resp = await asyncio.wait_for(read_message(vps_reader), timeout=10.0)

            if resp and resp.get("status") == "success":
                # Successfully connected and authenticated
                consecutive_failures = 0  # Reset failure counter
                logging.info("="*70)
                logging.info("✓ AUTHENTICATED WITH VPS SUCCESSFULLY!")
                logging.info("="*70)
                write_status("VPS_CONNECTED", f"{host}:{port}")
                
                # Run communication loops until connection breaks
                try:
                    await asyncio.gather(
                        send_to_vps_loop(vps_writer, heartbeat_interval),
                        receive_from_vps_loop(vps_reader)
                    )
                except Exception as e:
                    logging.warning(f"VPS connection interrupted: {e}")
                    # Will reconnect automatically
            else:
                # Authentication failed
                error_msg = resp.get("message", "Unknown error") if resp else "No response"
                logging.error(f"✗ VPS authentication failed: {error_msg}")
                logging.error(f"Check that secret_key matches VPS server configuration")
                write_status("VPS_AUTH_FAILED", error_msg)
                consecutive_failures += 1
                
        except ConnectionRefusedError:
            consecutive_failures += 1
            logging.error(f"✗ Connection refused by VPS at {host}:{port}")
            logging.error(f"The VPS server may not be running or the port is incorrect")
            write_status("VPS_CONNECTION_REFUSED", f"{host}:{port}")
            
        except asyncio.TimeoutError:
            consecutive_failures += 1
            logging.error(f"✗ Connection/authentication timeout to VPS at {host}:{port}")
            logging.error(f"The VPS may be unreachable or overloaded")
            write_status("VPS_TIMEOUT", f"{host}:{port}")
            
        except OSError as e:
            consecutive_failures += 1
            if e.errno == 10061:  # Windows: No connection could be made
                logging.error(f"✗ Cannot reach VPS at {host}:{port} - No route to host")
            elif e.errno == 11001:  # Windows: Host not found
                logging.error(f"✗ Cannot resolve hostname: {host}")
            else:
                logging.error(f"✗ Network error connecting to VPS: {e}")
            write_status("VPS_NETWORK_ERROR", str(e))
            
        except Exception as e:
            consecutive_failures += 1
            logging.error(f"✗ Unexpected VPS connection error: {e}", exc_info=True)
            write_status("VPS_ERROR", str(e))
            
        finally:
            # Always cleanup connection objects
            if vps_writer:
                try:
                    vps_writer.close()
                    await vps_writer.wait_closed()
                except:
                    pass
            vps_reader = vps_writer = None
            
            # Calculate reconnect delay with exponential backoff (capped)
            # Starts at 10s, increases to max 60s for persistent failures
            base_delay = 10
            reconnect_delay = min(
                base_delay + (consecutive_failures * 5),
                max_reconnect_delay
            )
            
            # Log reconnection info
            if consecutive_failures == 1:
                logging.info(f"⟳ Will retry connection in {reconnect_delay}s...")
            elif consecutive_failures <= 5:
                logging.info(f"⟳ Retrying connection in {reconnect_delay}s... (failure #{consecutive_failures})")
            elif consecutive_failures % 10 == 0:
                # Log every 10th failure to avoid log spam
                logging.warning(f"⟳ Still attempting reconnection after {consecutive_failures} failures...")
                logging.warning(f"⟳ Next retry in {reconnect_delay}s. Bridge continues accepting EA signals.")
            
            write_status("VPS_RECONNECTING", f"Attempt in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)

async def send_to_vps_loop(writer: StreamWriter, heartbeat_interval: int):
    """Send queued messages to VPS with heartbeat"""
    while True:
        try:
            msg = await asyncio.wait_for(vps_send_queue.get(), timeout=heartbeat_interval)
            await write_message(writer, msg)
            vps_send_queue.task_done()
            logging.info(f"→ Forwarded to VPS: {msg.get('action', 'unknown')} for {msg.get('symbol', 'unknown')}")
        except asyncio.TimeoutError:
            # Send heartbeat
            await write_message(writer, {"type": "ping"})
            logging.debug("→ Sent heartbeat to VPS")
        except Exception as e:
            logging.error(f"Error in send_to_vps_loop: {e}")
            break

async def receive_from_vps_loop(reader: StreamReader):
    """Receive and process messages from VPS"""
    while True:
        resp = await read_message(reader)
        if not resp:
            logging.warning("VPS connection closed")
            break

        if resp.get("type") == "pong":
            logging.debug("← Received pong from VPS")
            continue

        logging.info(f"← Received from VPS: {resp}")

        # Relay confirmation to EA if applicable
        cid = resp.get("client_msg_id") or resp.get("open_client_msg_id")
        if cid and cid in client_map:
            try:
                ea_writer = client_map[cid]
                await write_message(ea_writer, resp)
                logging.info(f"✓ Relayed VPS response to EA for msg_id: {cid}")
            except Exception as e:
                logging.warning(f"Failed to relay to EA {cid}: {e}")
                # Clean up dead connection
                if cid in client_map:
                    del client_map[cid]

# --- Local EA server ---
async def handle_ea_client(reader: StreamReader, writer: StreamWriter):
    """Handle individual EA client connection"""
    peer = writer.get_extra_info("peername")
    logging.info(f"✓ EA connected from: {peer}")
    
    client_msg_ids = set()

    try:
        while True:
            msg = await read_message(reader)
            if not msg:
                break

            logging.info(f"← From EA: {msg}")

            # Handle pings from EA
            if msg.get("type") == "ping":
                await write_message(writer, {"type": "pong"})
                logging.debug("→ Responded to EA ping")
                continue

            # Process trading signals
            action = msg.get("action", "").upper()
            if action in ["BUY", "SELL", "CLOSE"]:
                symbol = msg.get("symbol")
                
                if not symbol:
                    logging.warning("⚠ Signal missing 'symbol' field")

                # Track this client's message IDs
                cid = msg.get("client_msg_id")
                if cid:
                    client_map[cid] = writer
                    client_msg_ids.add(cid)

                # Forward to VPS
                if vps_writer:
                    await vps_send_queue.put(msg)
                    logging.info(f"✓ Queued signal for VPS: {action} {symbol}")
                else:
                    # VPS not connected - queue will hold signal until reconnection
                    await vps_send_queue.put(msg)
                    queue_size = vps_send_queue.qsize()
                    logging.warning(f"⚠ VPS offline - Signal queued for delivery when connection restored")
                    logging.warning(f"⚠ Signals in queue: {queue_size}")
                    
                    # Send acknowledgment to EA that signal is queued (not lost)
                    ack = {
                        "status": "queued",
                        "message": f"VPS offline. Signal queued for delivery. Queue size: {queue_size}",
                        "client_msg_id": cid
                    }
                    await write_message(writer, ack)
                    logging.info(f"✓ Sent queue acknowledgment to EA")

    except ConnectionResetError:
        logging.info(f"✗ EA connection reset: {peer}")
    except Exception as e:
        logging.error(f"Error handling EA client {peer}: {e}", exc_info=True)
    finally:
        # Clean up all message IDs for this client
        for msg_id in client_msg_ids:
            if msg_id in client_map:
                del client_map[msg_id]
        
        logging.info(f"✗ EA disconnected: {peer}. Cleaned up {len(client_msg_ids)} message IDs.")
        writer.close()
        await writer.wait_closed()

async def start_local_server_with_retry():
    """Start local server for EA connections with retry on failure"""
    local_host = CONFIG.get('bridge', 'local_host', fallback='127.0.0.1')
    local_port = CONFIG.getint('bridge', 'local_port', fallback=5050)

    while True:
        try:
            server = await asyncio.start_server(
                handle_ea_client,
                local_host,
                local_port,
                reuse_address=True
            )
            logging.info("="*70)
            logging.info(f"✓ Local EA server started: {local_host}:{local_port}")
            logging.info("="*70)
            write_status("EA_SERVER_RUNNING", f"{local_host}:{local_port}")
            
            async with server:
                await server.serve_forever()
                
        except OSError as e:
            if e.errno == 10048:  # Windows: Address already in use
                logging.error(f"✗ Port {local_port} is already in use!")
                logging.error(f"Another instance may be running or the port needs time to release.")
            else:
                logging.error(f"✗ Failed to bind to {local_host}:{local_port}: {e}")
            
            write_status("EA_SERVER_FAILED", f"Port {local_port} in use")
            logging.info(f"Retrying in 10s...")
            await asyncio.sleep(10)
            
        except Exception as e:
            logging.error(f"✗ Unexpected error in EA server: {e}", exc_info=True)
            write_status("EA_SERVER_ERROR", str(e))
            await asyncio.sleep(10)

async def main():
    """Main application entry point"""
    global CONFIG
    
    # Setup logging first
    setup_logging()
    
    # Load and validate config
    CONFIG = load_config()
    
    # Print summary
    logging.info("Configuration loaded successfully:")
    logging.info(f"  VPS: {CONFIG.get('server', 'vps_host')}:{CONFIG.get('server', 'vps_port')}")
    logging.info(f"  Local EA Port: {CONFIG.get('bridge', 'local_port')}")
    logging.info(f"  Heartbeat: {CONFIG.get('timing', 'heartbeat_interval')}s")
    
    write_status("STARTING")
    
    # Suppress noisy asyncio logs
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Start main application tasks
    vps_task = asyncio.create_task(vps_client_handler())
    server_task = asyncio.create_task(start_local_server_with_retry())
    
    # Run all tasks
    await asyncio.gather(vps_task, server_task)


if __name__ == "__main__":
    print_startup_info()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n" + "="*70)
        print("Bridge shutting down (Ctrl+C pressed)...")
        print("="*70)
        logging.info("Bridge shutting down by user request.")
    except Exception as e:
        print("\n" + "="*70)
        print(f"FATAL ERROR: {e}")
        print("="*70)
        logging.critical(f"Fatal error: {e}", exc_info=True)
        input("\nPress Enter to exit...")
    finally:
        write_status("STOPPED")