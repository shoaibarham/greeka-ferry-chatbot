"""
Script to load historical ferry data from JSON file into a SQLite database.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a log file for data updates
log_file = "data_updates.log"
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

def create_historical_tables(cursor):
    """
    Create the historical_date_ranges table in the SQLite database if it does not already exist.
    This table stores historical data on when routes were available in the past.
    """
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_date_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin_code TEXT,
            origin_name TEXT,
            destination_code TEXT,
            destination_name TEXT,
            start_date TEXT,
            end_date TEXT,
            appear_date TEXT
        )
    ''')

def extract_port_codes(port_name_with_code):
    """
    Extract port code and name from the combined format (e.g., 'HYD___Ydra' -> ('HYD', 'Ydra')).
    
    Args:
        port_name_with_code: String in the format "CODE___NAME"
        
    Returns:
        tuple: (code, name)
    """
    if '___' in port_name_with_code:
        parts = port_name_with_code.split('___')
        return (parts[0], parts[1])
    return (port_name_with_code, port_name_with_code)  # If no separator, return the input as both code and name

def insert_historical_data(cursor, data):
    """
    Insert historical data into the database tables from the provided JSON data.
    
    Args:
        cursor: Database cursor
        data: JSON data containing historical route information
    """
    for item in data:
        origin_name = item.get('origin_name', '')
        destination_name = item.get('destination_name', '')
        
        # Extract codes and names
        origin_code, origin_name_clean = extract_port_codes(origin_name)
        destination_code, destination_name_clean = extract_port_codes(destination_name)
        
        for date_range in item.get('dateRanges', []):
            start_date = date_range.get('startDate', '')
            end_date = date_range.get('endDate', '')
            appear_date = date_range.get('appearDate', '')
            
            cursor.execute('''
                INSERT INTO historical_date_ranges 
                (origin_code, origin_name, destination_code, destination_name, start_date, end_date, appear_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                origin_code, 
                origin_name_clean, 
                destination_code, 
                destination_name_clean, 
                start_date, 
                end_date, 
                appear_date
            ))

def load_historical_data(json_path='./attached_assets/GTFS appear dates.json', db_path='previous_db.db'):
    """
    Load historical data from a JSON file into the SQLite database.
    
    Args:
        json_path (str): Path to the JSON data file
        db_path (str): Path to the SQLite database
    
    Returns:
        str: Status message
    """
    try:
        logger.info(f"Loading historical data from {json_path} into {db_path}")
        
        # Connect to (or create) the SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create tables
        create_historical_tables(cursor)
        
        # Clear existing data
        logger.info("Clearing existing historical data...")
        cursor.execute("DELETE FROM historical_date_ranges")

        # Load JSON data from file
        logger.info(f"Loading historical JSON data from {json_path}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Insert data into the database
        logger.info("Inserting historical data into the database...")
        insert_historical_data(cursor, data)

        # Commit the changes and close the connection
        conn.commit()
        
        # Get the count of inserted records
        cursor.execute("SELECT COUNT(*) FROM historical_date_ranges")
        count = cursor.fetchone()[0]
        logger.info(f"Inserted {count} historical date range records")
        
        conn.close()

        logger.info("Historical data loaded successfully into the database")
        
        # Write to the log file
        with open(log_file, "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Historical data loaded successfully into {db_path}\n")
        
        return f"Historical data loaded successfully into {db_path} ({count} records)"
        
    except Exception as e:
        logger.error(f"Error loading historical data: {str(e)}", exc_info=True)
        return f"Error loading historical data: {str(e)}"

if __name__ == "__main__":
    try:
        result = load_historical_data()
        print(result)
    except Exception as e:
        logger.error(f"Error running historical data script: {str(e)}", exc_info=True)
        print(f"Error running historical data script: {str(e)}")
        exit(1)
    exit(0)