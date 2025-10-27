
import asyncio
import json
import logging
import ssl
from asyncio import StreamReader, StreamWriter

# Configure these to match your server settings
SERVER_HOST = "35.208.6.252"  # Use the GCP instance IP when testing remotely
SERVER_PORT = 5200
SECRET_KEY = "LZ2QThkLXWjmUCIADhLDu8tz4UwwQ35RnP3Bks76tjI"  # Must match the key in your .env file
USE_SSL = False  # Set to True if your server uses SSL

# SSL certificate for client-side validation (if server requires it)
# If the server's cert is self-signed, you might need to provide the CA cert here.
# If the server uses a trusted CA, this might not be needed.
CLIENT_CERT_PATH = None # "path/to/your/cert.pem"
CLIENT_KEY_PATH = None # "path/to/your/key.pem"
SERVER_CERT_PATH = None # "path/to/server/cert.pem" # For self-signed server certs

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def read_message(reader: StreamReader) -> dict | None:
    """Reads a length-prefixed JSON message from the stream."""
    try:
        header = await reader.readexactly(4)
        msg_len = int.from_bytes(header, 'big')
        payload = await reader.readexactly(msg_len)
        message = json.loads(payload.decode('utf-8'))
        logging.info(f"Received: {message}")
        return message
    except (asyncio.IncompleteReadError, ConnectionResetError):
        logging.warning("Connection closed by server.")
        return None
    except Exception as e:
        logging.error(f"Failed to read or decode message: {e}")
        return None

async def write_message(writer: StreamWriter, data: dict):
    """Writes a length-prefixed JSON message to the stream."""
    try:
        payload = json.dumps(data).encode('utf-8')
        header = len(payload).to_bytes(4, 'big')
        writer.write(header + payload)
        await writer.drain()
        logging.info(f"Sent: {data}")
    except Exception as e:
        logging.error(f"Failed to write message: {e}")

async def run_test_client():
    """Connects to the server, authenticates, and sends test signals."""
    ssl_context = None
    if USE_SSL:
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        if SERVER_CERT_PATH:
            ssl_context.load_verify_locations(SERVER_CERT_PATH)
        if CLIENT_CERT_PATH and CLIENT_KEY_PATH:
            ssl_context.load_cert_chain(certfile=CLIENT_CERT_PATH, keyfile=CLIENT_KEY_PATH)
        # Allow self-signed certificates if needed for testing
        # ssl_context.check_hostname = False
        # ssl_context.verify_mode = ssl.CERT_NONE


    try:
        reader, writer = await asyncio.open_connection(
            SERVER_HOST, SERVER_PORT, ssl=ssl_context
        )
    except ConnectionRefusedError:
        logging.error(f"Connection refused. Is the server running at {SERVER_HOST}:{SERVER_PORT}?")
        return
    except Exception as e:
        logging.error(f"Failed to connect: {e}")
        return

    peername = writer.get_extra_info('peername')
    logging.info(f"Connected to {peername}")

    try:
        # 1. Authenticate
        auth_payload = {"secret_key": SECRET_KEY}
        await write_message(writer, auth_payload)

        # Wait for server's auth confirmation
        auth_response = await reader.read(1024)
        if auth_response.decode().strip() == "Authentication successful.":
            logging.info("Authentication successful.")
        else:
            logging.error("Authentication failed. Server response: " + auth_response.decode())
            return

        # 2. Send a BUY signal
        buy_signal = {"action": "BUY", "symbol": "EURUSD", "price": 1.08500}
        await write_message(writer, buy_signal)
        response = await read_message(reader)
        if response and response.get("status") == "success":
            open_signal_id = response.get("signal_id")
            logging.info(f"Successfully opened BUY signal with ID: {open_signal_id}")

            # 3. Send a SELL signal
            await asyncio.sleep(2) # Wait a moment
            sell_signal = {"action": "SELL", "symbol": "GBPUSD", "price": 1.27300}
            await write_message(writer, sell_signal)
            await read_message(reader)


            # 4. Send a CLOSE signal for the first trade
            await asyncio.sleep(2) # Wait a moment
            if open_signal_id:
                close_signal = {
                    "action": "CLOSE",
                    "symbol": "EURUSD",
                    "price": 1.09000,
                    "open_signal_id": open_signal_id
                }
                await write_message(writer, close_signal)
                await read_message(reader)

        else:
            logging.error("Failed to process BUY signal.")


    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
    finally:
        logging.info("Closing the connection.")
        writer.close()
        await writer.wait_closed()

if __name__ == "__main__":
    if SECRET_KEY == "YOUR_SECURE_SECRET_KEY_HERE":
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! WARNING: Please set the SECRET_KEY in this script. !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        asyncio.run(run_test_client())
