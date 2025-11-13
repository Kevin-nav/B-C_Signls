import pytest
from unittest.mock import patch, AsyncMock

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

# A known valid secret key for testing, can be anything for tests
VALID_SECRET_KEY = "test-secret"

@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """
    Fixture to patch the global settings object for all tests in this file.
    """
    monkeypatch.setattr("app.core.config.settings.WEBHOOK_SECRET_KEY", VALID_SECRET_KEY)
    monkeypatch.setattr("app.core.config.settings.MAX_SIGNALS_PER_DAY", 10)
    monkeypatch.setattr("app.core.config.settings.MIN_SECONDS_BETWEEN_SIGNALS", 60)

async def test_health_check(test_client):
    """
    Tests if the /health endpoint is reachable and returns a healthy status.
    """
    response = await test_client.get("/health")
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "healthy"
    assert json_response["bot_active"] is True

async def test_receive_signal_success(test_client, mock_telegram_send_alert):
    """
    Tests a successful signal submission with an ATR value.
    """
    payload = {
        "secret_key": VALID_SECRET_KEY,
        "action": "BUY",
        "symbol": "EURUSD",
        "price": 1.10000,
        "atr": 0.00500
    }
    
    response = await test_client.post("/signal", json=payload)
    
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "success"
    assert json_response["signal_id"] is not None
    
    # Check that the telegram alert was called
    mock_telegram_send_alert.assert_called_once()
    # Check the content of the alert
    message = mock_telegram_send_alert.call_args[0][0]
    assert f"<b>BUY SIGNAL: {payload['symbol']}</b>" in message
    assert "➡️  <b>Entry:</b>" in message
    assert "🔴  <b>Stop:</b>" in message
    assert "🎯  <b>TP 1:</b>" in message
    assert "Practice proper risk management" in message

async def test_receive_signal_unauthorized(test_client):
    """
    Tests that a request with an invalid secret key is rejected.
    """
    payload = {
        "secret_key": "invalid-secret",
        "action": "BUY",
        "symbol": "EURUSD",
        "price": 1.10000
    }
    
    response = await test_client.post("/signal", json=payload)
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid secret key"

async def test_receive_signal_invalid_action(test_client):
    """
    Tests that a signal with an invalid action is rejected.
    """
    payload = {
        "secret_key": VALID_SECRET_KEY,
        "action": "HOLD",
        "symbol": "EURUSD",
        "price": 1.10000
    }
    
    response = await test_client.post("/signal", json=payload)
    
    assert response.status_code == 400
    assert "Action must be BUY, SELL, or CLOSE" in response.json()["detail"]

async def test_rate_limit_hit(test_client):
    """
    Tests that the rate limit is correctly triggered.
    We mock the can_send_signal function to simulate this condition.
    """
    payload = {
        "secret_key": VALID_SECRET_KEY,
        "action": "BUY",
        "symbol": "USDJPY",
        "price": 150.00
    }

    # Use patch to mock the can_send_signal method for this test only
    with patch("app.services.signal_service.signal_service.can_send_signal", return_value=(False, "Rate limit active")) as mock_can_send:
        response = await test_client.post("/signal", json=payload)
        
        # Verify our mock was called
        mock_can_send.assert_called_once()
        
        # Verify the response
        assert response.status_code == 429
        assert "Rate limit active" in response.json()["detail"]
