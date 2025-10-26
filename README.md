# B/C Signals - Trading Signal Bot

B/C Signals is a Python-based application that acts as a bridge between a trading source (like an MQL5 Expert Advisor) and a Telegram channel. It receives trading signals via a secure webhook, records them in a database, and broadcasts them to designated Telegram chats. Administrators can manage the bot's settings and view statistics directly through a Telegram command interface.

## Key Features

-   **Secure Webhook API**: Receives `BUY`, `SELL`, and `CLOSE` signals via an HTTP endpoint secured with a secret key.
-   **Telegram Bot Interface**: A full-featured bot for administrators to manage the system.
    -   View daily trading statistics (`/stats`).
    -   Pause and resume signal processing (`/pause`, `/resume`).
    -   Dynamically manage the list of Telegram channels receiving signals (`/chats`).
    -   Change operational settings like rate limits and trading hours in real-time (`/set`).
-   **Database Persistence**: All signals, chats, and settings are stored in a robust SQLite database.
-   **Dynamic Configuration**: Settings can be updated live via the bot without needing to restart the application. Initial defaults are loaded from a `.env` file.
-   **Flexible Signal Limits**: Protects against signal spam by enforcing a minimum time between signals and a daily signal limit, which can be set to a specific number or to "unlimited".
-   **Dynamic Statistics Display**: The `/stats` command intelligently hides profit/loss details if no trades have been closed, providing a cleaner view for signal-only usage.
-   **Trading Hours**: Can be configured to only process signals within a specific UTC time window.

---

## Setup and Installation

Follow these steps to set up and run the application.

### 1. Prerequisites

-   Python 3.10+
-   A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
-   Your Telegram User ID (for admin access)

### 2. Clone the Repository

```bash
git clone <your-repository-url>
cd AutoSig
```

### 3. Set Up a Virtual Environment

It is highly recommended to use a virtual environment to manage dependencies.

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies

Install all the required Python packages using the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a `.env` file by copying the example file and filling in the required values.

```bash
# Copy the example file
copy .env.example .env
```

Now, open the `.env` file and edit the following:

-   `TELEGRAM_BOT_TOKEN`: Your token from BotFather.
-   `TELEGRAM_DEFAULT_CHAT_ID`: The main channel/group ID where the bot will operate.
-   `WEBHOOK_SECRET_KEY`: A long, random string you create. This key is used to authorize requests from your MQL5 EA.
-   `ADMIN_USER_IDS`: Your personal Telegram User ID. You can get this from [@userinfobot](https://t.me/userinfobot).

### 6. Initialize the Database

The first time you run the application, it will automatically create the `trading_signals.db` file and all the necessary tables.

---

## Running the Application

To run the server, use `uvicorn`. The application will be accessible at `http://0.0.0.0:5000`.

```bash
python main.py
```

The server will start, initialize the database (if it's the first run), and the Telegram bot will begin polling for messages.

-   To run in development mode with auto-reload, set `RELOAD_UVICORN=True` in your `.env` file. **Note:** This is not recommended for production as it can cause issues with the Telegram bot's polling.

---

## Usage

### Telegram Bot Commands (Admin Only)

-   `/start`: Initializes the bot.
-   `/stats`: Shows today's trading statistics (total signals, wins, losses, P&L).
-   `/pause`: Pauses the processing of new signals from the webhook.
-   `/resume`: Resumes signal processing.
-   `/set`: Opens an interactive menu to change settings. For `MAX_SIGNALS_PER_DAY`, you can enter a number or `unlimited`.
-   `/chats`: Opens a menu to list, add, or remove Telegram chats that receive signals.
-   `/help`: Displays a list of available commands and current settings.
-   `/cancel`: Cancels any ongoing multi-step operation (like adding a chat).

### API Endpoint for MQL5

The application exposes a single endpoint for receiving signals:

-   **URL**: `http://<your_server_ip>:5000/signal`
-   **Method**: `POST`
-   **Content-Type**: `application/json`

For detailed instructions on how to send requests from an MQL5 Expert Advisor, please see the [MQL5 Integration Guide](MQL5_Integration_Guide.md).
