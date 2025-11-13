# Guide to Telegram Bot Commands

This document provides a detailed guide to the administrative commands available through the Telegram bot interface. These commands are essential for managing, configuring, and monitoring the bot in real-time.

## Admin Authorization

First and foremost, all administrative commands are restricted. For any of these commands to work, the Telegram User ID of the person issuing the command must be listed in the `ADMIN_USER_IDS` setting in your `.env` configuration file.

If a non-authorized user attempts to use a command, they will receive a simple "⛔️ Unauthorized" message.

---

## Command Reference

### Basic Operational Commands

These commands are for direct, immediate control over the bot's core function.

#### `/pause`
-   **Purpose**: To immediately stop the bot from processing any new incoming signals.
-   **How it Works**: This command sets the `bot_active` flag in the `system_state` database table to `false`. The `SignalService` checks this flag before processing any signal. If it's false, the signal is rejected with the message "Bot is currently paused by an admin."
-   **Usefulness**: This is critical for maintenance, emergency stops during unexpected market behavior, or for preventing signals during a specific period without changing the trading hours.

#### `/resume`
-   **Purpose**: To re-enable signal processing after it has been paused.
-   **How it Works**: It sets the `bot_active` flag back to `true`.
-   **Usefulness**: Allows the bot to safely resume normal operations after a manual pause.

#### `/stats`
-   **Purpose**: To get a quick, real-time overview of the day's performance.
-   **How it Works**: It queries the `signals` table to calculate and display key metrics for the current day (UTC).
-   **Information Displayed**:
    -   Total signals sent today vs. the daily limit.
    -   A breakdown of BUY vs. SELL signals.
    -   The number of closed trades.
    -   A Win/Loss count for closed trades.
    -   The total Profit & Loss (P&L) for all closed trades today.
    -   The current bot status (Active or Paused).
-   **Usefulness**: This is the most frequently used command for daily monitoring. It provides a vital health check and performance summary at a glance.

### Interactive Configuration Commands

These commands use Telegram's inline keyboards and conversation handlers to guide the admin through a series of steps, making configuration safe and user-friendly.

#### `/set`
-   **Purpose**: To change the bot's operational parameters on-the-fly without restarting the application.
-   **How it Works**: This command starts an interactive session.
    1.  The bot presents a menu of changeable settings (e.g., "Max Signals Per Day").
    2.  The admin chooses a setting.
    3.  The bot displays the current value and prompts for a new one, providing specific instructions (e.g., "Please send the new value in HH:MM format").
    4.  The bot validates the new value. If invalid, it prompts again.
    5.  If valid, the value is saved to the `settings` table in the database and the in-memory configuration is immediately updated.
-   **Changeable Settings**:
    -   `MAX_SIGNALS_PER_DAY`
    -   `MIN_SECONDS_BETWEEN_SIGNALS`
    -   `TRADING_START_TIME`
    -   `TRADING_END_TIME`
-   **Usefulness**: Extremely useful for adapting the bot to changing market conditions. An admin can tighten rate limits during high volatility or adjust trading hours without any downtime.

#### `/chats`
-   **Purpose**: To manage the list of Telegram channels or groups where signal alerts are broadcast.
-   **How it Works**: This command starts a menu-driven session.
    -   **List Current Chats**: Shows all configured chats with their names and IDs. It also cleverly refreshes the chat names by calling the Telegram API, so if a channel name is changed, it gets updated in the bot's database.
    -   **Add a New Chat**: Prompts the admin to send a new chat ID. It validates that the ID is in the correct format and that the bot is a member of that chat before adding it.
    -   **Remove a Chat**: Presents a list of configured chats to be removed. It prevents the admin from removing the primary `TELEGRAM_DEFAULT_CHAT_ID`.
-   **Usefulness**: Provides flexible control over where alerts are sent. You can easily add new subscriber channels or remove old ones.

#### `/cancel`
-   **Purpose**: To exit an interactive command session (`/set`, `/chats`, `/reports`) at any time.
-   **Usefulness**: A necessary utility to prevent getting stuck in a conversation with the bot.

### System Diagnostics

#### `/help`
-   **Purpose**: To display a summary of available commands and current rate-limiting settings.
-   **Usefulness**: A quick reference for admins.

--- 

## In-Depth: The `/reports` Command and Report Generation

The reporting system is a crucial diagnostic feature that provides insight into non-critical failures within the bot, particularly within the resilient `QueueService`.

### How Reports are Generated

Reports are **not** generated manually. They are created **automatically** by the system when specific, noteworthy events occur. The primary source of reports is the `QueueService`, which handles failed signals.

A signal might fail to process initially due to a temporary issue (like a database lock or a network hiccup). When this happens, the signal is sent to the `QueueService` for a retry. The service will then generate a report under two conditions:

1.  **`RETRY_FAILURE`**: The service attempts to re-process the signal up to a configured number of times (`MAX_RETRIES`, which is 5). If all retry attempts fail, the service gives up to prevent an infinite loop. It then:
    -   Logs a `RETRY_FAILURE` report to the database with the details of the discarded signal.
    -   Sends a direct notification to all admins stating that a signal failed processing and that they should use `/reports` to view the details.

2.  **`STALE_SIGNAL`**: A signal is not meant to be processed indefinitely. If a signal sits in the retry queue for too long (longer than `SIGNAL_EXPIRY_MINUTES`, which is 3 minutes), it's considered "stale" and no longer relevant. The `QueueService` will:
    -   Discard the signal without further retries.
    -   Log a `STALE_SIGNAL` report to the database.
    -   Notify the admins that a stale signal was discarded.

### How to Use the `/reports` Command

The `/reports` command is the interface for viewing these automatically generated logs.

-   **Purpose**: To allow an admin to investigate the details of failed signals or other system events that were not critical enough to halt the bot but are important to be aware of.

-   **How it Works**:
    1.  When an admin sends `/reports`, the bot queries the database for any reports where `is_read` is `FALSE`.
    2.  If there are no unread reports, it simply says so.
    3.  If there are unread reports, it displays them as an inline keyboard. Each button shows the report's timestamp and type (e.g., "2025-11-01 15:30 - Retry Failure").
    4.  The admin clicks on a report they wish to view.
    5.  The bot then retrieves the full `details` of that report from the database, displays them to the admin, and crucially, **updates the report's `is_read` flag to `TRUE`**. This means the report will not show up in the list the next time `/reports` is used.

-   **Usefulness**: This command is essential for debugging and maintaining a healthy system. If admins receive a notification about a failed signal, they can use `/reports` to see the exact signal data (symbol, price, etc.) that was discarded. This can help identify transient database issues, problems with a specific symbol, or other underlying problems that may need attention. It provides a clean and effective way to inspect low-priority failures without having to manually parse raw log files.