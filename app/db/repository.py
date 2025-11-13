import sqlite3
from datetime import datetime

def save_signal(
    conn: sqlite3.Connection, 
    action: str, 
    symbol: str, 
    price: float,
    atr: float | None,
    stop_loss: float | None,
    take_profit_1: float | None,
    take_profit_2: float | None,
    take_profit_3: float | None
) -> int:
    """Save a new signal to the database."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO signals 
            (action, symbol, price, atr, stop_loss, take_profit_1, take_profit_2, take_profit_3, sent_to_telegram) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)
        """,
        (action, symbol, price, atr, stop_loss, take_profit_1, take_profit_2, take_profit_3)
    )
    signal_id = cursor.lastrowid
    conn.commit()
    return signal_id

def close_signal(conn: sqlite3.Connection, signal_id: int, close_price: float) -> float:
    """Update a signal with close information and calculate P&L."""
    cursor = conn.cursor()
    cursor.execute("SELECT action, price FROM signals WHERE id = ?", (signal_id,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"Signal with ID {signal_id} not found.")

    action, open_price = result
    pl = (close_price - open_price) if action == "BUY" else (open_price - close_price)

    cursor.execute(
        """
        UPDATE signals
        SET closed = TRUE, close_price = ?, close_timestamp = CURRENT_TIMESTAMP, profit_loss = ?
        WHERE id = ?
        """,
        (close_price, pl, signal_id)
    )
    conn.commit()
    return pl

def get_today_signal_count(conn: sqlite3.Connection) -> int:
    """Get the count of signals sent today."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM signals WHERE DATE(timestamp) = DATE('now')")
    return cursor.fetchone()[0]

def get_today_stats(conn: sqlite3.Connection) -> dict:
    """Get detailed statistics for today's signals."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as buys,
            SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as sells,
            SUM(CASE WHEN closed = TRUE THEN 1 ELSE 0 END) as closed,
            SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses,
            SUM(profit_loss) as total_pl
        FROM signals
        WHERE DATE(timestamp) = DATE('now')
        """
    )
    row = cursor.fetchone()
    return {
        "total_signals": row["total"] or 0,
        "buys": row["buys"] or 0,
        "sells": row["sells"] or 0,
        "closed": row["closed"] or 0,
        "wins": row["wins"] or 0,
        "losses": row["losses"] or 0,
        "total_pl": row["total_pl"] or 0.0
    }

def get_bot_state(conn: sqlite3.Connection) -> bool:
    """Check if the bot is active/paused from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_state WHERE key = 'bot_active'")
    result = cursor.fetchone()
    return result[0] == 'true' if result else True

def set_bot_state(conn: sqlite3.Connection, active: bool):
    """Set the bot's active state in the database."""
    value = 'true' if active else 'false'
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE system_state SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'bot_active'",
        (value,)
    )
    conn.commit()

# =====================================================================
# Chat Management Functions
# =====================================================================

def get_all_chats(conn: sqlite3.Connection) -> list:
    """Fetch all managed chats from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, chat_name FROM managed_chats ORDER BY chat_name")
    return cursor.fetchall()

def add_chat(conn: sqlite3.Connection, chat_id: str, chat_name: str):
    """Add or update a chat in the database."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO managed_chats (chat_id, chat_name) VALUES (?, ?)",
        (chat_id, chat_name)
    )
    conn.commit()

def remove_chat(conn: sqlite3.Connection, chat_id: str):
    """Remove a chat from the database."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM managed_chats WHERE chat_id = ?", (chat_id,))
    conn.commit()

# =====================================================================
# Settings Management Functions
# =====================================================================

def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    """Fetch a specific setting's value from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    return result[0] if result else None

def set_setting(conn: sqlite3.Connection, key: str, value: str):
    """Add or update a setting in the database."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()

def load_settings_from_db(conn: sqlite3.Connection) -> dict:
    """Load all settings from the database into a dictionary."""
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    return {row['key']: row['value'] for row in cursor.fetchall()}

# =====================================================================
# Reports Management Functions
# =====================================================================

def create_report(conn: sqlite3.Connection, report_type: str, details: str):
    """Saves a new system report to the database."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reports (report_type, details) VALUES (?, ?)",
        (report_type, details)
    )
    conn.commit()

def get_unread_reports(conn: sqlite3.Connection) -> list:
    """Fetch all unread reports from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, report_type FROM reports WHERE is_read = FALSE ORDER BY timestamp DESC")
    return cursor.fetchall()

def get_report_details(conn: sqlite3.Connection, report_id: int) -> str | None:
    """Fetch the full details of a specific report and mark it as read."""
    cursor = conn.cursor()
    cursor.execute("SELECT details FROM reports WHERE id = ?", (report_id,))
    result = cursor.fetchone()
    if result:
        cursor.execute("UPDATE reports SET is_read = TRUE WHERE id = ?", (report_id,))
        conn.commit()
        return result['details']
    return None
