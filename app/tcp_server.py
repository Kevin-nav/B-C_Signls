import asyncio
import logging
import json
import ssl
from asyncio import StreamReader, StreamWriter

from app.core.config import settings
from app.db.database import get_db_connection
from app.services.signal_service import signal_service

logger = logging.getLogger(__name__)

async def handle_client(reader: StreamReader, writer: StreamWriter):
    """
    Coroutine to handle a single client connection.
    """
    peername = writer.get_extra_info('peername')
    logger.info(f"New connection from {peername}")

    try:
        # 1. Authentication
        auth_success = await authenticate_client(reader)
        if not auth_success:
            logger.warning(f"Authentication failed for {peername}. Closing connection.")
            return

        logger.info(f"Client {peername} authenticated successfully.")
        writer.write(b"Authentication successful.\n")
        await writer.drain()

        # 2. Main message loop
        while True:
            data = await read_message(reader)
            if data is None:
                logger.info(f"Client {peername} disconnected.")
                break

            # Process the received data
            response = await process_signal_data(data)
            await write_message(writer, response)

    except asyncio.CancelledError:
        logger.info(f"Connection to {peername} cancelled.")
    except ConnectionResetError:
        logger.info(f"Connection reset by {peername}.")
    except Exception as e:
        logger.error(f"An unexpected error occurred with client {peername}: {e}", exc_info=True)
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f"Connection with {peername} closed.")

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
    """
    try:
        # Read the 4-byte length header
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')

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
    """
    conn = None
    try:
        action = data.get("action", "").upper()
        symbol = data.get("symbol")
        price = data.get("price")
        open_signal_id = data.get("open_signal_id")

        if not all([action, symbol, price]):
            return {"status": "error", "message": "Missing required fields: action, symbol, price"}

        conn = get_db_connection()

        if action in ["BUY", "SELL"]:
            can_send, reason = signal_service.can_send_signal(conn)
            if not can_send:
                return {"status": "error", "message": reason}
            
            signal_id = await signal_service.process_new_signal(conn, action, symbol, price)
            message = f"Signal {action} processed successfully"
            return {"status": "success", "message": message, "signal_id": signal_id}

        elif action == "CLOSE":
            if not open_signal_id:
                return {"status": "error", "message": "open_signal_id is required for CLOSE action"}
            
            await signal_service.process_close_signal(conn, symbol, price, open_signal_id)
            message = f"Close signal for #{open_signal_id} processed successfully"
            return {"status": "success", "message": message, "signal_id": open_signal_id}

        else:
            return {"status": "error", "message": "Invalid action"}

    except Exception as e:
        logger.error(f"Error processing signal data: {e}", exc_info=True)
        return {"status": "error", "message": "An internal server error occurred."}
    finally:
        if conn:
            conn.close()

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
        ssl=ssl_context
    )

    addr = server.sockets[0].getsockname()
    protocol = "TCPS" if ssl_context else "TCP"
    logger.info(f"Serving on {addr} using {protocol}")

    async with server:
        await server.serve_forever()
