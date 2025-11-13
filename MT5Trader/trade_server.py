import asyncio
import configparser
import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from pydantic import BaseModel, Field

# =====================================================================
# Logging & Configuration
# =====================================================================

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def load_config():
    """Loads the configuration from config.ini"""
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

CONFIG = load_config()
SERVER_CONFIG = CONFIG['server']
SECURITY_CONFIG = CONFIG['security']
TRADING_DEFAULTS = CONFIG['trading_defaults']
RISK_CONFIG = CONFIG['risk_management']

# =====================================================================
# Pydantic Models for API
# =====================================================================

class TradeSignal(BaseModel):
    """Defines the structure for an incoming trade signal."""
    action: str = Field(..., description="Trade action: BUY or SELL")
    symbol: str = Field(..., description="Trading symbol (e.g., EURUSD)")
    price: float = Field(..., description="Entry price for the signal")
    stop_loss: float = Field(..., alias="sl")
    take_profit_1: float = Field(..., alias="tp1")
    take_profit_2: Optional[float] = Field(None, alias="tp2")
    take_profit_3: Optional[float] = Field(None, alias="tp3")

# =====================================================================
# Security Dependency
# =====================================================================

async def verify_secret_key(x_secret_key: str = Header(...)):
    """Dependency to verify the secret key in the request header."""
    if x_secret_key != SECURITY_CONFIG.get('secret_key'):
        raise HTTPException(status_code=401, detail="Invalid secret key")

# =====================================================================
# FastAPI Application
# =====================================================================

app = FastAPI(
    title="MT5 Trade Execution Server",
    dependencies=[Depends(verify_secret_key)]
)

@app.post("/signal")
async def receive_signal(signal: TradeSignal, background_tasks: BackgroundTasks):
    """
    Receives a trade signal and triggers the trade execution
    on all configured MT5 accounts in the background.
    """
    logging.info(f"Received signal: {signal.action} {signal.symbol} @ {signal.price}")
    background_tasks.add_task(execute_trade_on_all_accounts, signal)
    return {"status": "success", "message": "Signal received and queued for execution."}

@app.get("/health")
async def health_check():
    """A simple health check endpoint."""
    return {"status": "healthy"}

# =====================================================================
# MetaTrader 5 Core Logic
# =====================================================================

def get_mt5_accounts_from_config() -> List[dict]:
    """Parses the config.ini file to get a list of enabled MT5 accounts."""
    accounts = []
    for section in CONFIG.sections():
        if section.startswith("metatrader_"):
            if CONFIG.getboolean(section, 'enabled', fallback=False):
                accounts.append(dict(CONFIG.items(section)))
    logging.info(f"Found {len(accounts)} enabled MT5 accounts in config.")
    return accounts

def get_daily_pnl(magic_number: int) -> float:
    """Calculates the total profit/loss for today for a given magic number."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today, datetime.now(timezone.utc))
    
    if deals is None:
        logging.error(f"Failed to get trade history, error code = {mt5.last_error()}")
        return 0.0

    # Filter for closed trades with the correct magic number
    pnl = sum(d.profit for d in deals if d.magic == magic_number and d.entry == mt5.DEAL_ENTRY_OUT)
    logging.info(f"Today's PNL for magic number {magic_number}: {pnl:.2f}")
    return pnl

def calculate_lot_size(equity: float, risk_percent: float, sl_price: float, entry_price: float, symbol: str) -> float:
    """Calculates a safe lot size based on risk percentage and stop loss."""
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logging.error(f"Could not get symbol info for {symbol} to calculate lot size.")
        return 0.0

    # Get symbol properties
    min_lot = symbol_info.volume_min
    max_lot = symbol_info.volume_max
    lot_step = symbol_info.volume_step
    point_value = symbol_info.point
    contract_size = symbol_info.trade_contract_size

    # Calculate risk amount and stop loss distance
    risk_amount = equity * (risk_percent / 100.0)
    sl_distance_points = abs(entry_price - sl_price)
    
    if sl_distance_points == 0:
        logging.warning("Stop loss distance is zero. Cannot calculate lot size.")
        return min_lot

    # Calculate value of one lot's movement by 1 point
    one_lot_value_per_point = contract_size * point_value

    # Calculate ideal lot size
    ideal_lot_size = risk_amount / (sl_distance_points * one_lot_value_per_point)
    
    # Normalize the lot size according to the symbol's rules
    ideal_lot_size = (ideal_lot_size // lot_step) * lot_step
    ideal_lot_size = round(ideal_lot_size, 2) # Round to 2 decimal places for safety

    # Enforce broker limits
    if ideal_lot_size < min_lot:
        logging.warning(f"Calculated lot size {ideal_lot_size} is below minimum {min_lot}. Using minimum lot size.")
        return min_lot
    if ideal_lot_size > max_lot:
        logging.warning(f"Calculated lot size {ideal_lot_size} is above maximum {max_lot}. Using maximum lot size.")
        return max_lot
        
    return ideal_lot_size

def determine_trade_count(equity: float) -> int:
    """Determines how many trades to open based on account equity."""
    tier_3_balance = RISK_CONFIG.getfloat('tp_tier_3_balance', 100)
    tier_2_balance = RISK_CONFIG.getfloat('tp_tier_2_balance', 50)

    if equity >= tier_3_balance:
        return 3
    if equity >= tier_2_balance:
        return 2
    return 1

async def execute_trade_on_all_accounts(signal: TradeSignal):
    """
    Iterates through all configured accounts, checks risk, and places trades.
    """
    accounts = get_mt5_accounts_from_config()
    magic_number = TRADING_DEFAULTS.getint('magic_number', 234567)

    for account_config in accounts:
        account_num = account_config.get('mt5_account')
        password = account_config.get('mt5_password')
        server = account_config.get('mt5_server')
        path = account_config.get('mt5_path') or None

        logging.info(f"--- Processing account: {account_num} ---")

        # 1. Initialize & Login
        if not mt5.initialize(path=path) or not mt5.login(login=int(account_num), password=password, server=server):
            logging.error(f"MT5 connection/login failed for account {account_num}, error: {mt5.last_error()}")
            mt5.shutdown()
            continue
        
        logging.info(f"Successfully connected and logged into account {account_num}")

        # 2. Check Daily Loss Limit
        account_info = mt5.account_info()
        if not account_info:
            logging.error("Failed to get account info. Skipping trade.")
            mt5.shutdown()
            continue
        
        equity = account_info.equity
        daily_loss_limit_percent = RISK_CONFIG.getfloat('daily_loss_limit_percent', 0)

        if daily_loss_limit_percent > 0:
            pnl_today = get_daily_pnl(magic_number)
            loss_limit_amount = equity * (daily_loss_limit_percent / 100.0)
            if pnl_today < 0 and abs(pnl_today) >= loss_limit_amount:
                logging.warning(f"Daily loss limit of {daily_loss_limit_percent}% has been reached. PNL today: {pnl_today:.2f}. No new trades will be opened.")
                mt5.shutdown()
                continue

        # 3. Prepare Symbol and Trade Parameters
        symbol = signal.symbol
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.warning(f"Symbol {symbol} not found, attempting to enable it.")
            mt5.symbol_select(symbol, True)
            await asyncio.sleep(1)
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logging.error(f"Failed to find/enable symbol {symbol}. Skipping trade for this account.")
                mt5.shutdown()
                continue

        # 4. Calculate Lot Size
        risk_percent = RISK_CONFIG.getfloat('risk_per_trade_percent', 1.0)
        total_lot_size = calculate_lot_size(equity, risk_percent, signal.stop_loss, signal.price, symbol)
        if total_lot_size == 0.0:
            logging.error("Calculated lot size is zero. Cannot place trade.")
            mt5.shutdown()
            continue
        
        # 5. Determine Number of Trades
        num_trades = determine_trade_count(equity)
        lot_per_trade = round((total_lot_size / num_trades) / symbol_info.volume_step) * symbol_info.volume_step
        lot_per_trade = max(lot_per_trade, symbol_info.volume_min) # Ensure it's not below min
        
        logging.info(f"Total Lot: {total_lot_size}, Trades to open: {num_trades}, Lot per trade: {lot_per_trade}")

        if lot_per_trade < symbol_info.volume_min:
            logging.error(f"Lot per trade ({lot_per_trade}) is smaller than the minimum allowed ({symbol_info.volume_min}). Aborting.")
            mt5.shutdown()
            continue

        # 6. Place the Trades
        order_type = mt5.ORDER_TYPE_BUY if signal.action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        take_profits = [signal.take_profit_1, signal.take_profit_2, signal.take_profit_3]
        
        for i in range(num_trades):
            tp = take_profits[i]
            if tp is None:
                logging.warning(f"TP{i+1} is not available. Skipping trade {i+1}.")
                continue

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_per_trade,
                "type": order_type,
                "price": mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid,
                "sl": signal.stop_loss,
                "tp": tp,
                "deviation": TRADING_DEFAULTS.getint('slippage', 20),
                "magic": magic_number,
                "comment": f"SignalBot_TP{i+1}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK, # Hardcoded to FOK as we only trade synthetics for now
            }

            logging.info(f"Sending order {i+1}/{num_trades} for {symbol}: {request}")
            result = mt5.order_send(request)

            if result is None:
                logging.error(f"order_send() failed, error code = {mt5.last_error()}")
            elif result.retcode != mt5.TRADE_RETCODE_DONE:
                logging.error(f"Order {i+1} failed! retcode={result.retcode}, comment={result.comment}")
            else:
                logging.info(f"Order {i+1} successfully placed! ticket={result.order}")
            
            await asyncio.sleep(0.2) # Small delay between placing orders

        # 7. Shutdown connection
        logging.info(f"Finished processing account {account_num}.")
        mt5.shutdown()
        await asyncio.sleep(1)

# =====================================================================
# Main Entry Point
# =====================================================================

if __name__ == "__main__":
    uvicorn.run(
        "trade_server:app",
        host=SERVER_CONFIG.get('host', '0.0.0.0'),
        port=SERVER_CONFIG.getint('port', 8000),
        reload=False
    )