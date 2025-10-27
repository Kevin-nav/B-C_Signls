# B/C Signals - Trading Signal to Telegram Bot

This project is a robust, high-performance server designed to receive trading signals from an MQL5 Expert Advisor (or any other source) via a TCP connection and instantly relay them as formatted alerts to designated Telegram channels.

Built with Python and `asyncio`, it's engineered for low latency and high concurrency, capable of handling multiple trading bots simultaneously. It includes a suite of professional features for reliability, monitoring, and administration.

![Signal Example](https://i.imgur.com/your-image-link.png) <!-- Replace with an actual image of a Telegram signal -->

---

## ✨ Key Features

- **High-Performance TCP Server**: Uses `asyncio` for non-blocking I/O to handle numerous concurrent client connections with minimal overhead.
- **Persistent Connections**: Clients connect once and maintain a stable, long-lived TCP session for ultra-low-latency signal delivery.
- **Robust Heartbeat Mechanism**: An application-level "ping/pong" heartbeat automatically detects and prunes dead or zombie connections.
- **Smart Retry Queue**: Failed signals due to temporary database issues are automatically queued and retried. Stale signals (older than 3 minutes) are discarded to ensure timeliness.
- **Structured JSON Logging**: All events are logged in a structured JSON format with daily log rotation, making it easy to monitor, parse, and debug.
- **Connection Tracing**: Each client connection is assigned a unique ID, allowing for easy tracing of a single session through the logs.
- **Telegram Bot Admin Interface**: A full-featured bot interface for administrators.
  - `/stats`: View real-time trading statistics for the day.
  - `/pause` & `/resume`: Globally pause or resume signal processing.
  - `/set`: Interactively change bot settings (e.g., max signals per day) on the fly.
  - `/chats`: Dynamically manage which Telegram channels or groups receive signals.
  - `/reports`: View detailed reports on system events, such as discarded stale signals.
- **Dynamic Configuration**: Core settings can be changed live via the Telegram bot without needing to restart the server.
- **Secure**: Uses a secret key for client authentication and enforces message size limits to prevent abuse.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- An active Telegram Bot and its API Token (get from [@BotFather](https://t.me/BotFather))
- Your personal Telegram User ID (get from [@userinfobot](https://t.me/userinfobot))

### 1. Clone & Setup

```bash
# Clone the repository
git clone https://github.com/Kevin-nav/B-C_Signls.git
cd B-C_Signls

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

1.  Rename `.env.example` to `.env`.
2.  Open the `.env` file and fill in the required values:
    - `TELEGRAM_BOT_TOKEN`: Your bot's API token.
    - `TELEGRAM_DEFAULT_CHAT_ID`: The main public channel ID for signals.
    - `WEBHOOK_SECRET_KEY`: A long, random string for security. You can generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
    - `ADMIN_USER_IDS`: A comma-separated list of Telegram User IDs for admins (e.g., `12345678,98765432`).

### 3. Running the Server

Once configured, you can run the server:

```bash
python main.py
```

The server will start, initialize the database (`trading_signals.db`), and begin listening for TCP connections on port `5200` and HTTP traffic on port `5000`.

---

## 🤖 Telegram Bot Commands

All commands must be sent in a private message to the bot from a registered admin user.

- `/start` or `/help`: Shows the welcome message and command list.
- `/stats`: Displays a summary of today's trading activity (total signals, buys/sells, wins/losses, P&L).
- `/pause`: Temporarily stops the bot from processing any new incoming signals.
- `/resume`: Resumes normal signal processing.
- `/set`: Starts an interactive conversation to change live settings like `MAX_SIGNALS_PER_DAY`.
- `/chats`: Allows you to add or remove channels/groups that will receive signal alerts.
- `/reports`: Shows a list of system-generated reports (e.g., stale signals) for review.

---

##  MQL5 Integration Protocol

Your MQL5 client should connect to the server using the following TCP protocol:

1.  **Connection**: Establish a persistent TCP connection to the server's IP on port `5200`.
2.  **Framing**: All messages (client-to-server and server-to-client) must be prefixed with a 4-byte, big-endian integer representing the length of the following UTF-8 JSON payload.
3.  **Authentication**: Immediately after connecting, send a JSON authentication message:
    ```json
    { "secret_key": "YOUR_SECRET_KEY" }
    ```
4.  **Heartbeat**: Send a JSON ping message every 30 seconds to keep the connection alive:
    ```json
    { "type": "ping" }
    ```
5.  **Signal Messages**: Send trade signals as a JSON payload:
    ```json
    {
      "client_msg_id": "2025-10-28-01",
      "action": "BUY",
      "symbol": "EURUSD",
      "price": 1.12500
    }
    ```

The server will respond to each message with a length-prefixed JSON confirmation.