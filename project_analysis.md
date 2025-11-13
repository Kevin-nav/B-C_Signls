# In-Depth Project Analysis: Trading Signal Bot

This document provides a detailed breakdown of the features and architecture of the "B/C Signals" trading bot based on an analysis of its source code.

## 1. Overall Architecture

The system is a sophisticated Python application built around the **FastAPI** framework. It's designed to be robust, configurable, and resilient. The architecture consists of several key components that work in concert:

-   **FastAPI Web Server**: The primary entry point for HTTP-based signals. It exposes a RESTful API for receiving trading commands.
-   **Asynchronous TCP Server**: A dedicated, secure server running in parallel to handle direct connections from trading platforms like MetaTrader 5 (MQL5). This provides a lower-latency, persistent communication channel.
-   **Telegram Bot**: Serves as the administrative and notification interface. Admins can control the bot, view stats, and manage settings, while trading alerts are broadcasted to designated channels.
-   **SQLite Database**: A local SQLite database provides persistence for signals, application state, settings, and managed chats.
-   **Service Layer**: A set of well-defined services (`SignalService`, `TelegramService`, `QueueService`) encapsulates the core business logic, separating concerns and making the application modular.
-   **Asynchronous Tasking**: The application leverages Python's `asyncio` library extensively for non-blocking I/O, allowing it to handle web requests, TCP connections, and Telegram updates concurrently and efficiently.

The general flow is as follows:
1.  A signal is received via either the **FastAPI endpoint** or the **TCP server**.
2.  The signal is authenticated and validated.
3.  The `SignalService` applies a series of checks (bot status, rate limits, trading hours).
4.  If the checks pass, the signal is saved to the **SQLite database**.
5.  The `TelegramService` formats and sends an alert to all managed channels.
6.  If any part of the process fails (e.g., a temporary database lock), the `QueueService` can place the signal in a retry queue to be processed later.
7.  Admins can interact with the **Telegram Bot** at any time to monitor and control the system.

---

## 2. Configuration (`app.core.config`)

Configuration is managed centrally and dynamically, providing significant flexibility.

-   **Initial Load**: On startup, settings are loaded from a `.env` file into a Pydantic `Settings` model. This includes essential credentials like the Telegram token and secret keys.
-   **Dynamic Overrides**: After the initial load, the application connects to the database and loads any settings from the `settings` table. These values override the initial `.env` settings, allowing for dynamic reconfiguration without restarting the bot.
-   **Type Casting**: The `reload_settings_from_db` function is intelligent; it correctly parses and casts values from the database (which are stored as text) into their proper Python types (e.g., `int`, `bool`, `datetime.time`).
-   **Key Settings**:
    -   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DEFAULT_CHAT_ID`: For Telegram integration.
    -   `WEBHOOK_SECRET_KEY`: A crucial security key used to authenticate all incoming signals (both HTTP and TCP).
    -   `ADMIN_USER_IDS`: A list of Telegram user IDs who have administrative privileges.
    -   `MAX_SIGNALS_PER_DAY`, `MIN_SECONDS_BETWEEN_SIGNALS`: Core rate-limiting parameters.
    -   `TRADING_START_TIME`, `TRADING_END_TIME`: Defines the window during which the bot will accept signals.
    -   `TCP_HOST`, `TCP_PORT`, `SSL_CERT_PATH`, `SSL_KEY_PATH`: Configuration for the secure TCP server.

---

## 3. Database (`app.db`)

The application uses a local SQLite database, initialized on startup. The schema is defined in `app.db.database.py` and is comprised of five tables:

1.  **`signals`**: The main table for recording all trading activity.
    -   `id`: Primary key.
    -   `timestamp`, `action`, `symbol`, `price`: Core details of the signal.
    -   `closed`, `close_price`, `close_timestamp`, `profit_loss`: Fields to track the outcome of a trade when a "CLOSE" signal is received.
    -   `sent_to_telegram`, `telegram_message_id`: For tracking notifications.

2.  **`system_state`**: A simple key-value store for global application state.
    -   Its primary use is to store the `bot_active` flag, which allows admins to pause or resume the bot's operations globally.

3.  **`managed_chats`**: Stores the list of Telegram chats that should receive signal alerts.
    -   `chat_id`: The unique Telegram chat ID.
    -   `chat_name`: A user-friendly name for the chat, which is automatically updated by the bot.

4.  **`settings`**: A key-value table for storing the dynamic settings that override the `.env` file. This allows admins to change rate limits and trading hours via the Telegram interface without touching the server.

5.  **`reports`**: A table for logging significant system events that require admin attention.
    -   `report_type`: e.g., `STALE_SIGNAL`, `RETRY_FAILURE`.
    -   `details`: A JSON or text blob with the full context of the event.
    -   `is_read`: A flag to track whether an admin has viewed the report.

The `repository.py` file contains all the functions for interacting with these tables, providing a clean data access layer.

---

## 4. API Endpoints (FastAPI)

The FastAPI application (`main.py`, `app.api.endpoints.py`) provides the public-facing HTTP interface.

-   **`POST /signal`**: This is the main endpoint for receiving signals from external sources.
    1.  **Authentication**: It first checks for a valid `secret_key` in the request payload.
    2.  **Validation**: It ensures the `action` is one of "BUY", "SELL", or "CLOSE".
    3.  **Processing**: It calls the `signal_service` to handle the core logic.
    4.  **Error Handling**: It returns specific HTTP status codes for different failure scenarios (e.g., `401` for auth failure, `429` for rate limiting).
    5.  **Response**: On success, it returns a `SignalResponse` containing the status, a message, the newly created `signal_id`, and the total number of signals for the day.

-   **`GET /health`**: A simple health check endpoint that confirms the service is running and reports the current `bot_active` state from the database.

-   **`GET /stats`**: A public endpoint that provides a snapshot of the day's trading statistics, the bot's active status, and the current rate limits.

---

## 5. Secure TCP Server (`app.tcp_server.py`)

This is a powerful feature for direct integration with trading terminals like MT5. It runs in a separate asynchronous task, managed by the main application's lifecycle.

-   **SSL/TLS Encryption**: The server can be configured with SSL certificates (`cert.pem`, `key.pem`) to ensure all communication between the client (MT5) and the server is encrypted and secure.
-   **Asynchronous Handling**: It uses `asyncio.start_server` to handle multiple client connections concurrently without blocking.
-   **Custom Message Protocol**: It uses a length-prefixed JSON protocol for messaging. Each message is preceded by a 4-byte integer representing the length of the JSON payload. This is a robust way to handle message framing over a stream.
-   **Authentication**: The very first message a client sends must be a JSON object containing the `secret_key`. If the key is invalid, the server sends an error and immediately closes the connection.
-   **Heartbeat Mechanism**: The server loop uses an `asyncio.wait_for` with a 60-second timeout. If no message is received from the client within this period, the connection is considered stale and closed. The client is expected to send a `{"type": "ping"}` message periodically, to which the server replies `{"type": "pong"}`, keeping the connection alive.
-   **Thread-Safe Database Operations**: When processing a signal received via TCP, all database interactions (`can_send_signal`, `save_signal`, etc.) are wrapped in `asyncio.to_thread()`. This is critical because `sqlite3` operations are blocking, and running them in a separate thread prevents the entire server's event loop from freezing.

---

## 6. Telegram Bot (`app.services.telegram_service.py`)

The Telegram bot is the command and control center for the application. It uses the `python-telegram-bot` library and features a sophisticated setup with conversation handlers for interactive commands.

-   **Admin Authorization**: All administrative commands are protected by a check that verifies the user's ID against the `ADMIN_USER_IDS` list from the configuration.
-   **Core Commands**:
    -   `/pause` & `/resume`: Changes the `bot_active` flag in the `system_state` table, globally halting or resuming signal processing.
    -   `/stats`: Displays a detailed summary of the day's trading performance.
-   **Interactive Conversations**:
    -   **/set**: An interactive wizard that allows admins to change core settings (`MAX_SIGNALS_PER_DAY`, `MIN_SECONDS_BETWEEN_SIGNALS`, `TRADING_START_TIME`, `TRADING_END_TIME`). It guides the user with inline keyboards, validates the input, saves it to the `settings` table in the database, and then reloads the configuration in-memory.
    -   **/chats**: A menu-driven interface for managing the list of channels/groups that receive alerts. Admins can list, add, or remove chats. The bot validates new chat IDs and can even get the chat's name directly from the Telegram API. It also cleverly prevents the admin from removing the default chat channel.
    -   **/reports**: Allows admins to view system reports logged in the `reports` table. It presents a list of unread reports, and when one is selected, it displays the details and marks it as read.
-   **Alert Broadcasting**: The `send_alert` method iterates through all `managed_chats` in the database and sends the formatted signal message to each one.
-   **Admin Notifications**: The `notify_admins` method sends a direct message to each admin for critical events, such as a signal being discarded after multiple retry failures.

---

## 7. Core Services (`app.services`)

The business logic is cleanly separated into three main services.

### `SignalService`

This is the central processing unit for signals.
-   **`can_send_signal`**: This is the gatekeeper method. Before processing any new signal, it performs a sequence of checks:
    1.  Is the bot paused (`get_bot_state`)?
    2.  Is the current time within `TRADING_START_TIME` and `TRADING_END_TIME`?
    3.  Has enough time passed since the last signal (`MIN_SECONDS_BETWEEN_SIGNALS`)?
    4.  Has the daily signal limit (`MAX_SIGNALS_PER_DAY`) been reached?
-   **Signal Processing**: The `process_new_signal` and `process_close_signal` methods orchestrate the workflow: saving to the database, formatting the message, and calling the `telegram_service` to send the alert.
-   **Message Formatting**: It contains private methods (`_format_signal_message`, `_format_close_message`) that create the nicely formatted HTML messages sent to Telegram, complete with emojis and up-to-date stats.

### `QueueService`

This service adds a layer of resilience to the bot.
-   **Background Worker**: It runs a background `asyncio` task that processes items from a queue.
-   **Retry Logic**: If a signal fails to process (e.g., due to a temporary database error), it can be added to this queue. The worker will attempt to re-process it after a delay (`RETRY_DELAY`).
-   **Stale Signal Handling**: It won't retry a signal forever. If a signal has been in the queue for longer than `SIGNAL_EXPIRY_MINUTES`, it is discarded.
-   **Failure Reporting**: If a signal fails all `MAX_RETRIES`, it is permanently discarded. In both cases (stale or max retries), a report is created in the `reports` table and a notification is sent to the admins.

### `TelegramService`

As described in its own section, this service encapsulates all interactions with the Telegram API, from command handling to sending messages.

---

## 8. Logging (`app.core.logging_config.py`)

-   **Structured JSON Logging**: The application is configured to output logs in a structured JSON format. This is ideal for modern log management systems (like ELK stack or Datadog), as it makes logs easy to parse, search, and filter.
-   **Daily Rotation**: Log files are automatically rotated daily (e.g., `bot_2025-11-01.log`), preventing single log files from growing indefinitely.
-   **Dual Output**: Logs are sent to both the rotating file (in JSON format) and the console (in a human-readable format) for easier development and debugging.
