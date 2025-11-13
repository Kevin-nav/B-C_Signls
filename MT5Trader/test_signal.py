# -*- coding: utf-8 -*-
import requests
import configparser
import logging

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def get_server_config():
    """Reads server and security config from the ini file."""
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    if 'server' not in config or 'security' not in config:
        raise ValueError("Config file must contain [server] and [security] sections.")
        
    server_conf = config['server']
    security_conf = config['security']
    
    # The public IP of the VPS where the server is running
    host = "185.167.99.205"
    
    if 'port' not in server_conf:
        raise ValueError("port not found in [server] section of config.ini")
    port = server_conf.get('port')
        
    url = f"http://{host}:{port}/signal"
    secret_key = security_conf.get('secret_key')
    
    if not secret_key:
        raise ValueError("secret_key not found in [security] section of config.ini")
        
    return url, secret_key

def send_test_signal():
    """Sends a predefined test signal to the trading server."""
    try:
        url, secret_key = get_server_config()
    except Exception as e:
        logging.error(f"Error reading configuration: {e}")
        return

    # --- Define the Test Signal ---
    # This is a sample BUY signal for a synthetic index.
    # The prices are examples; the server will use the current market price for entry.
    payload = {
        "action": "BUY",
        "symbol": "Volatility 75 Index",
        "price": 350000.0,  # The entry price in the signal is for reference
        "sl": 349000.0,
        "tp1": 351000.0,
        "tp2": 352000.0,
        "tp3": 353000.0
    }

    headers = {
        "X-Secret-Key": secret_key,
        "Content-Type": "application/json"
    }

    logging.info(f"Sending test signal to: {url}")
    logging.info(f"Payload: {payload}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        logging.info(f"Server responded with status code: {response.status_code}")
        
        # Try to print JSON response, fall back to text if it fails
        try:
            logging.info(f"Response body: {response.json()}")
        except requests.exceptions.JSONDecodeError:
            logging.info(f"Response body (non-JSON): {response.text}")

    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred while sending the request: {e}")

if __name__ == "__main__":
    logging.info("--- MT5 Trader Test Script ---")
    logging.info("This script will send a single test signal to the running server.")
    send_test_signal()
    logging.info("--- Test complete ---")
