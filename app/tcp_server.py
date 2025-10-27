import asyncio
import logging
import json
import ssl
from asyncio import StreamReader, StreamWriter

import uuid

from app.core.config import settings
from app.db.database import create_bot_connection
from app.services.signal_service import signal_service

logger = logging.getLogger(__name__)

async def handle_client(reader: StreamReader, writer: StreamWriter):
    """
    Coroutine to handle a single client connection.
    """
    peername = writer.get_extra_info('peername')
    client_id = str(uuid.uuid4()).split('-')[0] # Short, unique ID
    log_extra = {'extra_data': {'client_id': client_id, 'peername': peername}}
    logger.info(f"New connection from {peername}", extra=log_extra)

    try:
        # 1. Authentication
        auth_success = await authenticate_client(reader)
        if not auth_success:
            logger.warning(f"Authentication failed for {peername}. Sending error and closing connection.", extra=log_extra)
            await write_message(writer, {"status": "error", "message": "Invalid secret key"})
            return

        logger.info(f"Client {peername} authenticated successfully.", extra=log_extra)
        await write_message(writer, {"status": "success", "message": "Authentication successful"})

        # 2. Main message loop with heartbeat
        HEARTBEAT_TIMEOUT = 60.0  # seconds
        while True:
            try:
                # Wait for a message with a timeout
                data = await asyncio.wait_for(read_message(reader), timeout=HEARTBEAT_TIMEOUT)
                
                if data is None:
                    logger.info(f"Client {peername} disconnected gracefully.", extra=log_extra)
                    break

                # Handle heartbeat messages
                if data.get("type") == "ping":
                    await write_message(writer, {"type": "pong"})
                    continue

                # Process regular signal data
                response = await process_signal_data(data)
                await write_message(writer, response)

            except asyncio.TimeoutError:
                logger.warning(f"Connection to {peername} timed out after {HEARTBEAT_TIMEOUT} seconds. Closing.", extra=log_extra)
                break

    except asyncio.CancelledError:
        logger.info(f"Connection to {peername} cancelled.")
    except ConnectionResetError:
        logger.info(f"Connection reset by {peername}.", extra=log_extra)
    except Exception as e:
        logger.error(f"An unexpected error occurred with client {peername}: {e}", exc_info=True, extra=log_extra)
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f"Connection with {peername} closed.", extra=log_extra)

async def authenticate_client(reader: StreamReader) -> bool:
    """
    Reads the secret key from the client and validates it.
    """
    try:
        message = await read_message(reader)
        if message and message.get("secret_key") == settings.WEBHOOK_SECRET_KEY:
            return True
        return False
    except Exception as e:
        logger.error(f"Error during authentication: {e}")
        return False

async def read_message(reader: StreamReader) -> dict | None:
    """
    Reads a length-prefixed JSON message from the stream.
    Includes a size limit to prevent DoS attacks.
    """
    MAX_MESSAGE_SIZE = 4 * 1024 * 1024  # 4 MB
    try:
        # Read the 4-byte length header
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')

        if msg_len > MAX_MESSAGE_SIZE:
            logger.warning(f"Message size {msg_len} exceeds limit of {MAX_MESSAGE_SIZE}. Closing connection.")
            return None # Returning None will cause the handler to close the connection

        # Read the JSON payload
        payload = await reader.readexactly(msg_len)
        return json.loads(payload.decode('utf-8'))
    except (asyncio.IncompleteReadError, ConnectionResetError):
        return None # Client disconnected
    except Exception as e:
        logger.error(f"Failed to read or decode message: {e}")
        return None

async def write_message(writer: StreamWriter, data: dict):
    """
    Writes a length-prefixed JSON message to the stream.
    """
    try:
        payload = json.dumps(data).encode('utf-8')
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
    except Exception as e:
        logger.error(f"Failed to write message: {e}")

async def process_signal_data(data: dict) -> dict:
    """
    Processes the signal data using the existing signal_service.
    All database operations are run in a separate thread to avoid blocking the event loop.
    """
    conn = None
    try:
        action = data.get("action", "").upper()
        symbol = data.get("symbol")
        price = data.get("price")
        open_signal_id = data.get("open_signal_id")

        # Base response structure
        response = {"client_msg_id": data.get("client_msg_id")}

        if not all([action, symbol, price]):
            response.update({"status": "error", "message": "Missing required fields: action, symbol, price"})
            return response

        # 1. Create DB connection in a non-blocking way
        conn = await asyncio.to_thread(create_bot_connection)

        if action in ["BUY", "SELL"]:
            # 2. Run blocking DB checks in a thread
            can_send, reason = await asyncio.to_thread(signal_service.can_send_signal, conn)
            if not can_send:
                response.update({"status": "error", "message": reason})
                return response
            
            # 3. Process signal (which includes more blocking calls) in a thread
            # Note: process_new_signal is async because of telegram, but its DB part is blocking.
            # We can't use to_thread on the whole async function, so we refactor it.
            signal_id = await asyncio.to_thread(repository.save_signal, conn, action, symbol, price)
            logger.info(f"Signal saved to DB: ID={signal_id}, {action} {symbol} @ {price}")

            stats = await asyncio.to_thread(repository.get_today_stats, conn)
            message = signal_service._format_signal_message(action, symbol, price, signal_id, stats)
            await telegram_service.send_alert(message)

            signal_service.update_last_signal_time()
            
            message = f"Signal {action} processed successfully"
            response.update({"status": "success", "message": message, "signal_id": signal_id})
            return response

        elif action == "CLOSE":
            if not open_signal_id:
                response.update({"status": "error", "message": "open_signal_id is required for CLOSE action"})
                return response
            
            # 4. Process close signal (with blocking DB calls) in a thread
            try:
                pl = await asyncio.to_thread(repository.close_signal, conn, open_signal_id, price)
                logger.info(f"Signal {open_signal_id} closed: P&L={pl:.5f}")

                stats = await asyncio.to_thread(repository.get_today_stats, conn)
                message = signal_service._format_close_message(symbol, price, open_signal_id, pl, stats)
                await telegram_service.send_alert(message)

                message = f"Close signal for #{open_signal_id} processed successfully"
                response.update({"status": "success", "message": message, "signal_id": open_signal_id})
                return response
            except ValueError as e:
                logger.error(f"Error closing signal: {e}")
                response.update({"status": "error", "message": str(e)})
                return response

        else:
            response.update({"status": "error", "message": "Invalid action"})
            return response

    except Exception as e:
        logger.error(f"Error processing signal data: {e}", exc_info=True)
        return {"status": "error", "message": "An internal server error occurred."}
    finally:
        if conn:
            # 5. Close connection in a non-blocking way
            await asyncio.to_thread(conn.close)

async def start_tcp_server():
    """
    Initializes and starts the TCP server.
    """
    host = settings.TCP_HOST
    port = settings.TCP_PORT

    ssl_context = None
    if settings.SSL_CERT_PATH and settings.SSL_KEY_PATH:
        try:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=settings.SSL_CERT_PATH, keyfile=settings.SSL_KEY_PATH)
            logger.info("SSL context loaded successfully.")
        except FileNotFoundError:
            logger.error("SSL certificate or key file not found. Server will start without SSL.")
            ssl_context = None
        except Exception as e:
            logger.error(f"Error loading SSL context: {e}. Server will start without SSL.")
            ssl_context = None

    server = await asyncio.start_server(
        handle_client,
        host,
        port,
        reuse_address=True,
        ssl=ssl_context
    )

    addr = server.sockets[0].getsockname()
    protocol = "TCPS" if ssl_context else "TCP"
    logger.info(f"Serving on {addr} using {protocol}")

    async with server:
        await server.serve_forever()
