# migrate_db.py
# This script safely updates the 'signals' table in the database
# by adding new columns if they do not already exist.
# It is safe to run this script multiple times.

import sqlite3
import logging

# --- Configuration ---
DB_PATH = "trading_signals.db"
TABLE_NAME = "signals"
COLUMNS_TO_ADD = {
    "atr": "REAL",
    "stop_loss": "REAL",
    "take_profit_1": "REAL",
    "take_profit_2": "REAL",
    "take_profit_3": "REAL"
}

# --- Basic Logging ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def migrate_database():
    """
    Connects to the database and adds missing columns to the signals table.
    """
    logging.info(f"Connecting to database: {DB_PATH}")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get the list of existing columns in the table
        cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
        existing_columns = [row[1] for row in cursor.fetchall()]
        logging.info(f"Found existing columns: {existing_columns}")

        # Loop through the columns we want to add
        for column_name, column_type in COLUMNS_TO_ADD.items():
            if column_name not in existing_columns:
                try:
                    logging.info(f"Column '{column_name}' not found. Adding it to table '{TABLE_NAME}'...")
                    alter_query = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {column_name} {column_type}"
                    cursor.execute(alter_query)
                    logging.info(f"Successfully added column '{column_name}'.")
                except sqlite3.Error as e:
                    logging.error(f"Failed to add column '{column_name}'. Error: {e}")
            else:
                logging.info(f"Column '{column_name}' already exists. Skipping.")
        
        # Commit changes and close the connection
        conn.commit()
        logging.info("Database migration check complete. Changes have been committed.")

    except sqlite3.Error as e:
        logging.error(f"A database error occurred: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            logging.info("Database connection closed.")

if __name__ == "__main__":
    logging.info("--- Starting Database Migration ---")
    migrate_database()
    logging.info("--- Database Migration Finished ---")
