import pytest
from unittest.mock import MagicMock
from app.services.signal_service import SignalService

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_conn():
    """Fixture for a mock database connection."""
    return MagicMock()

@pytest.fixture
def signal_service():
    """Fixture to provide a SignalService instance for each test."""
    return SignalService()

async def test_process_new_buy_signal_with_atr(signal_service, mock_conn, mocker):
    """
    Verify that a BUY signal with ATR calculates SL/TP correctly and saves the data.
    """
    # --- Arrange ---
    action = "BUY"
    symbol = "EURUSD"
    price = 1.10000
    atr = 0.00500
    
    # Mock dependencies using mocker fixture
    mock_repo = mocker.patch("app.services.signal_service.repository")
    mock_send_alert = mocker.patch("app.services.signal_service.telegram_service.send_alert", new_callable=mocker.AsyncMock)
    
    # Mock repository return values
    mock_repo.get_bot_state.return_value = True
    mock_repo.get_today_signal_count.return_value = 0
    mock_repo.save_signal.return_value = 123  # Mock signal ID

    # Expected SL/TP values
    expected_sl = price - (atr * 1.5)
    expected_tp1 = price + (atr * 1.5)
    expected_tp2 = price + (atr * 3.0)
    expected_tp3 = price + (atr * 4.5)

    # --- Act ---
    signal_id = await signal_service.process_new_signal(
        mock_conn, action, symbol, price, atr
    )

    # --- Assert ---
    assert signal_id == 123

    # Verify save_signal was called correctly
    mock_repo.save_signal.assert_called_once()
    call_args = mock_repo.save_signal.call_args[0]
    
    assert call_args[0] == mock_conn
    assert call_args[1] == action
    assert call_args[2] == symbol
    assert call_args[3] == price
    assert call_args[4] == atr
    assert abs(call_args[5] - expected_sl) < 1e-5
    assert abs(call_args[6] - expected_tp1) < 1e-5
    assert abs(call_args[7] - expected_tp2) < 1e-5
    assert abs(call_args[8] - expected_tp3) < 1e-5

    # Verify Telegram alert was sent with the correct content
    mock_send_alert.assert_called_once()
    message = mock_send_alert.call_args[0][0]
    
    assert f"🟢 <b>{action} SIGNAL: {symbol}</b>" in message
    assert f"➡️  <b>Entry:</b>   <code>{price:.5f}</code>" in message
    assert f"🔴  <b>Stop:</b>    <code>{expected_sl:.5f}</code>" in message
    assert f"🎯  <b>TP 1:</b>    <code>{expected_tp1:.5f}</code>" in message
    assert "Practice proper risk management" in message

async def test_process_new_sell_signal_with_atr(signal_service, mock_conn, mocker):
    """
    Verify that a SELL signal with ATR calculates SL/TP correctly.
    """
    # --- Arrange ---
    action = "SELL"
    symbol = "GBPUSD"
    price = 1.25000
    atr = 0.01000
    
    mock_repo = mocker.patch("app.services.signal_service.repository")
    mock_send_alert = mocker.patch("app.services.signal_service.telegram_service.send_alert", new_callable=mocker.AsyncMock)
    
    mock_repo.get_bot_state.return_value = True
    mock_repo.get_today_signal_count.return_value = 0
    mock_repo.save_signal.return_value = 124

    # Expected SL/TP values (inverted for SELL)
    expected_sl = price + (atr * 1.5)
    expected_tp1 = price - (atr * 1.5)

    # --- Act ---
    await signal_service.process_new_signal(
        mock_conn, action, symbol, price, atr
    )

    # --- Assert ---
    mock_repo.save_signal.assert_called_once()
    call_args = mock_repo.save_signal.call_args[0]
    
    assert abs(call_args[5] - expected_sl) < 1e-5
    assert abs(call_args[6] - expected_tp1) < 1e-5

    mock_send_alert.assert_called_once()
    message = mock_send_alert.call_args[0][0]
    
    assert f"🔴 <b>{action} SIGNAL: {symbol}</b>" in message
    assert f"🔴  <b>Stop:</b>    <code>{expected_sl:.5f}</code>" in message
    assert f"🎯  <b>TP 1:</b>    <code>{expected_tp1:.5f}</code>" in message
    assert "Practice proper risk management" in message

async def test_process_new_signal_without_atr(signal_service, mock_conn, mocker):
    """
    Verify that a signal without ATR is processed without SL/TP.
    """
    # --- Arrange ---
    action = "BUY"
    symbol = "USDJPY"
    price = 150.00
    atr = None
    
    mock_repo = mocker.patch("app.services.signal_service.repository")
    mock_send_alert = mocker.patch("app.services.signal_service.telegram_service.send_alert", new_callable=mocker.AsyncMock)
    
    mock_repo.get_bot_state.return_value = True
    mock_repo.get_today_signal_count.return_value = 0
    mock_repo.save_signal.return_value = 125

    # --- Act ---
    await signal_service.process_new_signal(
        mock_conn, action, symbol, price, atr
    )

    # --- Assert ---
    mock_repo.save_signal.assert_called_once()
    call_args = mock_repo.save_signal.call_args[0]
    
    # Verify all SL/TP values are None
    assert call_args[4] is None  # atr
    assert call_args[5] is None  # stop_loss
    assert call_args[6] is None  # tp1
    assert call_args[7] is None  # tp2
    assert call_args[8] is None  # tp3

    mock_send_alert.assert_called_once()
    message = mock_send_alert.call_args[0][0]
    
    assert f"🟢 <b>{action} SIGNAL: {symbol}</b>" in message
    assert f"➡️  <b>Entry:</b>   <code>{price:.5f}</code>" in message
    # Ensure SL/TP info and disclaimer are NOT in the simple message
    assert "Stop:" not in message
    assert "TP 1:" not in message
    assert "Practice proper risk management" not in message
