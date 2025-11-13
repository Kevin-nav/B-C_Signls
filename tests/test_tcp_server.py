import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call

from app.tcp_server import handle_client
from app.core.config import settings

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

# Use the same valid secret key as other tests
VALID_SECRET_KEY = "test-secret"

def create_mock_streams(mocker, messages: list):
    """
    Helper function to create mock StreamReader and StreamWriter objects.
    This now correctly simulates the two-step read process (header, then payload).
    """
    reader = AsyncMock(spec=asyncio.StreamReader)
    
    # Create a sequence of chunks (header, payload, header, payload, ...)
    # that the server will read in sequence.
    chunks = []
    for msg in messages:
        payload = json.dumps(msg).encode('utf-8')
        header = len(payload).to_bytes(4, 'big')
        chunks.append(header)
        chunks.append(payload)

    # Configure the reader to return the chunks in sequence, then raise an exception
    # to simulate the client disconnecting, which breaks the server loop.
    reader.readexactly.side_effect = chunks + [asyncio.IncompleteReadError]

    writer = AsyncMock(spec=asyncio.StreamWriter)
    writer.get_extra_info.return_value = ('127.0.0.1', 12345) # Mock peername
    
    return reader, writer

async def test_handle_client_successful_signal(mocker, monkeypatch):
    """
    Tests the full flow for a valid client sending a valid signal via TCP.
    """
    # --- Arrange ---
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET_KEY', VALID_SECRET_KEY)
    
    # Mock the service layer that the TCP handler calls
    # We need to make the async method, process_new_signal, an AsyncMock
    mock_signal_service = mocker.patch("app.tcp_server.signal_service", new_callable=MagicMock)
    mock_signal_service.process_new_signal = AsyncMock(return_value=999)
    mock_signal_service.can_send_signal.return_value = (True, "OK")

    # Mock the DB connection factory, which is now called inside the service
    mocker.patch("app.services.signal_service.repository")
    mocker.patch("app.services.signal_service.telegram_service")
    mocker.patch("app.tcp_server.create_bot_connection")

    auth_message = {"secret_key": VALID_SECRET_KEY}
    signal_message = {
        "action": "BUY",
        "symbol": "TCPUSD",
        "price": 1.2345,
        "atr": 0.01,
        "client_msg_id": "tcp-test-1"
    }
    
    reader, writer = create_mock_streams(mocker, [auth_message, signal_message])

    # --- Act ---
    await handle_client(reader, writer)

    # --- Assert ---
    # 1. Check authentication response
    assert len(writer.write.call_args_list) == 2
    written_auth_response = writer.write.call_args_list[0].args[0][4:] # Skip 4-byte header
    assert json.loads(written_auth_response) == {"status": "success", "message": "Authentication successful"}

    # 2. Check that the signal service was called correctly
    # Note: can_send_signal is now called inside process_new_signal in the service,
    # so we check the top-level call.
    mock_signal_service.process_new_signal.assert_awaited_once_with(
        mocker.ANY, # the mock connection
        "BUY",
        "TCPUSD",
        1.2345,
        0.01
    )

    # 3. Check the final response to the client
    written_signal_response = writer.write.call_args_list[1].args[0][4:] # Skip 4-byte header
    response_data = json.loads(written_signal_response)
    assert response_data["status"] == "success"
    assert response_data["signal_id"] == 999
    assert response_data["client_msg_id"] == "tcp-test-1"

async def test_handle_client_auth_failure(mocker, monkeypatch):
    """
    Tests that an invalid secret key results in an error message and connection close.
    """
    # --- Arrange ---
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET_KEY', VALID_SECRET_KEY)
    
    auth_message = {"secret_key": "INVALID_KEY"}
    reader, writer = create_mock_streams(mocker, [auth_message])

    # --- Act ---
    await handle_client(reader, writer)

    # --- Assert ---
    # Check that an error message was written
    writer.write.assert_called_once()
    written_data = writer.write.call_args.args[0][4:] # Skip 4-byte header
    response_data = json.loads(written_data)
    assert response_data["status"] == "error"
    assert response_data["message"] == "Invalid secret key"

    # Check that the connection was closed
    writer.close.assert_called_once()
