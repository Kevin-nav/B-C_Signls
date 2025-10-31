# -*- coding: utf-8 -*-
import asyncio
import configparser
import json
import logging
import time
from asyncio import StreamReader, StreamWriter, Queue
from typing import Optional

# --- Configuration Loading ---
def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

CONFIG = load_config()

# --- Logging Setup ---
def setup_logging():
    log_format = '[%(asctime)s] %(levelname)s: %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format, datefmt='%Y-%m-%d %H:%M:%S')
    # Optional: Add file handler
    # handler = logging.FileHandler('bridge.log')
    # handler.setFormatter(logging.Formatter(log_format))
    # logging.getLogger().addHandler(handler)

# --- Global State ---
# These will hold the connection streams to the VPS
vps_reader: Optional[StreamReader] = None
vps_writer: Optional[StreamWriter] = None
# Queue for messages from the EA that need to be sent to the VPS
vps_send_queue = Queue()

# --- Low-level Message Framing ---
async def read_message(reader: StreamReader) -> Optional[dict]:
    try:
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')
        if msg_len > 4 * 1024 * 1024: # 4MB limit
            logging.error(f"Message size {msg_len} exceeds 4MB limit. Closing connection.")
            return None
        payload = await reader.readexactly(msg_len)
        return json.loads(payload.decode('utf-8'))
    except (asyncio.IncompleteReadError, ConnectionResetError):
        logging.warning("Connection closed by peer.")
    except Exception as e:
        logging.error(f"Failed to read or decode message: {e}")
    return None

async def write_message(writer: StreamWriter, data: dict):
    try:
        payload = json.dumps(data).encode('utf-8')
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
    except Exception as e:
        logging.error(f"Failed to write message: {e}")

# --- VPS Client Logic ---
async def vps_client_handler():
    """Manages the persistent connection to the remote VPS server."""
    global vps_reader, vps_writer
    host = CONFIG.get('server', 'vps_host')
    port = CONFIG.getint('server', 'vps_port')
    secret = CONFIG.get('security', 'secret_key')
    heartbeat_interval = CONFIG.getint('timing', 'heartbeat_interval')

    while True:
        try:
            logging.info(f"Connecting to VPS at {host}:{port}...")
            # Connect with a timeout
            vps_reader, vps_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), 
                timeout=CONFIG.getfloat('timing', 'connect_timeout')
            )
            logging.info("Connected to VPS. Authenticating...")

            # Authenticate
            await write_message(vps_writer, {"secret_key": secret})
            auth_response = await read_message(vps_reader)

            if auth_response and auth_response.get("status") == "success":
                logging.info("Authentication with VPS successful.")
                # Start heartbeat and message processing loops
                await asyncio.gather(
                    send_loop(vps_writer, heartbeat_interval),
                    receive_loop(vps_reader)
                )
            else:
                logging.error(f"VPS authentication failed: {auth_response}")

        except asyncio.TimeoutError:
            logging.error("Connection to VPS timed out.")
        except ConnectionRefusedError:
            logging.error("Connection to VPS refused. Is the server running?")
        except Exception as e:
            logging.error(f"VPS connection error: {e}")
        finally:
            if vps_writer:
                vps_writer.close()
                await vps_writer.wait_closed()
            vps_reader, vps_writer = None, None
            logging.info("Disconnected from VPS. Reconnecting in 10 seconds...")
            await asyncio.sleep(10) # Reconnect delay

async def send_loop(writer: StreamWriter, heartbeat_interval: int):
    """Handles sending queued messages and heartbeats to the VPS."""
    while True:
        try:
            # Wait for a message from the EA or for the heartbeat interval
            message = await asyncio.wait_for(vps_send_queue.get(), timeout=heartbeat_interval)
            await write_message(writer, message)
            logging.info(f"Forwarded message to VPS: {message}")
            vps_send_queue.task_done()
        except asyncio.TimeoutError:
            # No message from EA, send a heartbeat
            logging.info("Sending heartbeat to VPS...")
            await write_message(writer, {"type": "ping"})
        except Exception as e:
            logging.error(f"Error in send loop: {e}")
            break # Exit loop to trigger reconnect

async def receive_loop(reader: StreamReader):
    """Handles receiving messages (pongs, confirmations) from the VPS."""
    while True:
        response = await read_message(reader)
        if response is None:
            break # Connection closed
        
        if response.get("type") == "pong":
            logging.info("Received pong from VPS.")
        else:
            logging.info(f"Received confirmation from VPS: {response}")
            # Here you could add logic to pass confirmation back to the EA if needed

# --- Local EA Server Logic ---
async def handle_ea_client(ea_reader: StreamReader, ea_writer: StreamWriter):
    """Handles a connection from a single MQL5 EA client."""
    peername = ea_writer.get_extra_info('peername')
    logging.info(f"MQL5 EA client connected from {peername}")

    try:
        while True:
            message = await read_message(ea_reader)
            if message is None:
                break # EA disconnected

            logging.info(f"Received from EA: {message}")
            
            if vps_writer is None:
                logging.warning("VPS is not connected. Cannot forward signal.")
                # Optionally queue the message here for later sending
                error_response = {"status": "error", "message": "Server temporarily unavailable"}
                await write_message(ea_writer, error_response)
            else:
                # Put the message into the queue to be sent to the VPS
                await vps_send_queue.put(message)
                # For now, we send an immediate acknowledgment to the EA.
                # A more robust system might wait for the actual VPS confirmation.
                ack = {"status": "success", "message": "Signal received by bridge and queued for VPS."}
                await write_message(ea_writer, ack)

    except Exception as e:
        logging.error(f"Error with EA client {peername}: {e}")
    finally:
        logging.info(f"EA client {peername} disconnected.")
        ea_writer.close()
        await ea_writer.wait_closed()

async def main():
    setup_logging()
    local_host = CONFIG.get('bridge', 'local_host')
    local_port = CONFIG.getint('bridge', 'local_port')

    # Start the local server for the EA
    local_server = await asyncio.start_server(handle_ea_client, local_host, local_port)
    logging.info(f"Local bridge started. Listening for MQL5 EA on {local_host}:{local_port}")

    # Start the VPS client handler
    vps_client_task = asyncio.create_task(vps_client_handler())

    async with local_server:
        await local_server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bridge shutting down.")
